"""Tests for email_classifier.auth.oauth.

All tests use fakes — no real Google credentials or network calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from email_classifier.auth.oauth import (
    get_credentials,
    get_gmail_service,
    has_modify_scope,
)


# ─── helpers ──────────────────────────────────────────────────────────────────


def _write_fake_credentials(path: Path) -> None:
    """Write a minimal OAuth Desktop client secrets JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    secrets = {
        "installed": {
            "client_id": "fake-client-id.apps.googleusercontent.com",
            "client_secret": "fake-secret",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    path.write_text(json.dumps(secrets))


def _write_fake_token(path: Path, scopes: list[str] | None = None) -> None:
    """Write a minimal token JSON that looks valid to Credentials.from_authorized_user_file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    token = {
        "token": "ya29.fake-access-token",
        "refresh_token": "fake-refresh-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "fake-client-id.apps.googleusercontent.com",
        "client_secret": "fake-secret",
        "scopes": scopes or ["https://www.googleapis.com/auth/gmail.readonly"],
        "expiry": "2099-01-01T00:00:00Z",
    }
    path.write_text(json.dumps(token))


# ─── tests ────────────────────────────────────────────────────────────────────


class TestGetCredentials:
    def test_missing_credentials_exits(self, tmp_path: Path) -> None:
        """Missing credentials.json should exit with a friendly message."""
        cred_path = str(tmp_path / "no_such_file.json")
        with pytest.raises(SystemExit):
            get_credentials(
                credentials_path=cred_path,
                token_path=str(tmp_path / "token.json"),
            )

    def test_valid_token_loaded_without_network(self, tmp_path: Path) -> None:
        """A valid, non-expired token should be returned without hitting the network."""
        cred_path = tmp_path / "credentials.json"
        token_path = tmp_path / "token.json"
        _write_fake_credentials(cred_path)
        _write_fake_token(token_path)

        # Patch Credentials.valid to return True so no refresh is attempted.
        with patch(
            "email_classifier.auth.oauth.Credentials.from_authorized_user_file"
        ) as mock_from_file:
            fake_creds = MagicMock()
            fake_creds.valid = True
            mock_from_file.return_value = fake_creds

            result = get_credentials(
                credentials_path=str(cred_path),
                token_path=str(token_path),
            )

        assert result is fake_creds

    def test_runs_flow_when_no_token(self, tmp_path: Path) -> None:
        """When no token exists, InstalledAppFlow should be invoked."""
        cred_path = tmp_path / "credentials.json"
        token_path = tmp_path / "data" / "token.json"
        _write_fake_credentials(cred_path)
        # Do NOT write a token file.

        fake_creds = MagicMock()
        fake_creds.to_json.return_value = json.dumps({"token": "new"})

        with patch(
            "email_classifier.auth.oauth.InstalledAppFlow.from_client_secrets_file"
        ) as mock_flow_cls:
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = fake_creds
            mock_flow_cls.return_value = mock_flow

            result = get_credentials(
                credentials_path=str(cred_path),
                token_path=str(token_path),
            )

        mock_flow.run_local_server.assert_called_once()
        assert result is fake_creds
        # Token file should have been written.
        assert token_path.exists()

    def test_refresh_error_reruns_flow(self, tmp_path: Path) -> None:
        """A RefreshError should trigger re-running the OAuth flow."""
        from google.auth.exceptions import RefreshError

        cred_path = tmp_path / "credentials.json"
        token_path = tmp_path / "token.json"
        _write_fake_credentials(cred_path)
        _write_fake_token(token_path)

        expired_creds = MagicMock()
        expired_creds.valid = False
        expired_creds.expired = True
        expired_creds.refresh_token = "old-refresh-token"
        expired_creds.refresh.side_effect = RefreshError("token revoked")

        new_creds = MagicMock()
        new_creds.to_json.return_value = json.dumps({"token": "fresh"})

        with patch(
            "email_classifier.auth.oauth.Credentials.from_authorized_user_file",
            return_value=expired_creds,
        ), patch(
            "email_classifier.auth.oauth.InstalledAppFlow.from_client_secrets_file"
        ) as mock_flow_cls:
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = new_creds
            mock_flow_cls.return_value = mock_flow

            result = get_credentials(
                credentials_path=str(cred_path),
                token_path=str(token_path),
            )

        mock_flow.run_local_server.assert_called_once()
        assert result is new_creds


class TestHasModifyScope:
    def test_no_token_returns_false(self, tmp_path: Path) -> None:
        assert has_modify_scope(str(tmp_path / "no_token.json")) is False

    def test_readonly_token_returns_false(self, tmp_path: Path) -> None:
        token_path = tmp_path / "token.json"
        _write_fake_token(
            token_path,
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        assert has_modify_scope(str(token_path)) is False

    def test_modify_token_returns_true(self, tmp_path: Path) -> None:
        token_path = tmp_path / "token.json"
        _write_fake_token(
            token_path,
            scopes=["https://www.googleapis.com/auth/gmail.modify"],
        )
        assert has_modify_scope(str(token_path)) is True
