"""Tests for email_classifier.ingest (Gmail client mocks + runner).

All fixtures are synthetic — no real network calls or real email data.
Tests cover:
  * paginated messages.list
  * batch RAW get
  * incremental history sync
  * expired historyId fallback to full fetch
  * promotions_as handling
  * ingest runner integration (mocked service + DB)
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from email_classifier.config import AppConfig
from email_classifier.ingest.db import Database
from email_classifier.ingest.gmail import (
    HistoryExpiredError,
    _is_rate_limit,
    batch_get_messages,
    iter_history_changes,
    iter_message_ids,
)
from email_classifier.ingest.runner import run_ingest
from tests.conftest import make_gmail_message, make_raw_email


# ─── helpers ──────────────────────────────────────────────────────────────────


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _make_list_response(
    ids: list[str], next_page_token: str | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {"messages": [{"id": i} for i in ids]}
    if next_page_token:
        result["nextPageToken"] = next_page_token
    return result


def _make_raw_api_response(
    msg_id: str,
    thread_id: str = "t1",
    label_ids: list[str] | None = None,
    internal_date: int = 1_700_000_000_000,
    history_id: str = "10001",
) -> dict[str, Any]:
    raw = make_raw_email(subject="Fake subject", from_addr="fake@example.com")
    return {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": label_ids or ["INBOX"],
        "internalDate": internal_date,
        "historyId": history_id,
        "raw": _b64url(raw),
    }


# ─── iter_message_ids ─────────────────────────────────────────────────────────


class TestIterMessageIds:
    def test_single_page(self) -> None:
        service = MagicMock()
        resp = _make_list_response(["m1", "m2", "m3"])
        service.users().messages().list.return_value.execute.return_value = resp
        service.users().messages().list_next.return_value = None

        ids = list(iter_message_ids(service, page_size=500))
        assert ids == ["m1", "m2", "m3"]

    def test_two_pages(self) -> None:
        service = MagicMock()
        page1 = _make_list_response(["m1", "m2"], next_page_token="tok")
        page2 = _make_list_response(["m3", "m4"])

        req1 = MagicMock()
        req1.execute.return_value = page1
        req2 = MagicMock()
        req2.execute.return_value = page2

        service.users().messages().list.return_value = req1
        service.users().messages().list_next.side_effect = [req2, None]

        ids = list(iter_message_ids(service))
        assert ids == ["m1", "m2", "m3", "m4"]

    def test_max_messages_cap(self) -> None:
        service = MagicMock()
        resp = _make_list_response([f"m{i}" for i in range(10)])
        service.users().messages().list.return_value.execute.return_value = resp
        service.users().messages().list_next.return_value = None

        ids = list(iter_message_ids(service, max_messages=3))
        assert len(ids) == 3

    def test_empty_mailbox(self) -> None:
        service = MagicMock()
        service.users().messages().list.return_value.execute.return_value = {}
        service.users().messages().list_next.return_value = None

        ids = list(iter_message_ids(service))
        assert ids == []


# ─── batch_get_messages ───────────────────────────────────────────────────────


class TestBatchGetMessages:
    def _build_service_with_batch(self, api_responses: dict[str, Any]) -> MagicMock:
        """Build a mock service where batch.execute() calls the callback for each msg."""

        service = MagicMock()

        def fake_batch_execute() -> None:
            # Simulate Gmail batch callback invocation.
            for req_id, resp in api_responses.items():
                callback = service.new_batch_http_request.return_value._callbacks[req_id]
                callback(req_id, resp, None)

        batch = MagicMock()
        batch._callbacks: dict[str, Any] = {}

        def fake_add(request, request_id: str) -> None:
            # Store callback so execute() can call it.
            pass

        # We need a different approach since add() receives the callback via
        # new_batch_http_request(callback=...).
        captured: dict = {}

        def new_batch(callback):
            b = MagicMock()
            b._cb = callback
            b._added_ids: list[str] = []

            def add(request, request_id: str):
                b._added_ids.append(request_id)

            def execute():
                for rid in b._added_ids:
                    if rid in api_responses:
                        b._cb(rid, api_responses[rid], None)
                    else:
                        b._cb(rid, None, Exception(f"not found: {rid}"))

            b.add = add
            b.execute = execute
            return b

        service.new_batch_http_request.side_effect = new_batch
        return service

    def test_parses_raw_body(self) -> None:
        api_resp = _make_raw_api_response("m1", label_ids=["INBOX"])
        service = self._build_service_with_batch({"m1": api_resp})
        results = list(batch_get_messages(service, ["m1"], batch_size=50))
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "m1"
        assert isinstance(r["raw_bytes"], bytes)
        assert r["from_header"] is not None
        assert r["subject"] is not None

    def test_multiple_messages_in_chunk(self) -> None:
        responses = {f"m{i}": _make_raw_api_response(f"m{i}") for i in range(4)}
        service = self._build_service_with_batch(responses)
        results = list(batch_get_messages(service, list(responses), batch_size=50))
        assert len(results) == 4

    def test_batch_size_respected(self) -> None:
        """When batch_size=2 and 5 IDs, there should be 3 batch calls."""
        responses = {f"m{i}": _make_raw_api_response(f"m{i}") for i in range(5)}
        service = self._build_service_with_batch(responses)
        call_count = 0
        real_new_batch = service.new_batch_http_request.side_effect

        def counting_new_batch(callback):
            nonlocal call_count
            call_count += 1
            return real_new_batch(callback)

        service.new_batch_http_request.side_effect = counting_new_batch
        results = list(batch_get_messages(service, list(responses), batch_size=2))
        assert call_count == 3  # ceil(5/2) = 3


# ─── iter_history_changes ─────────────────────────────────────────────────────


class TestRateLimitDetect:
    def test_text_match(self) -> None:
        assert _is_rate_limit(RuntimeError("Rate Limit Exceeded")) is True
        assert _is_rate_limit(RuntimeError("userRateLimitExceeded")) is True
        assert _is_rate_limit(RuntimeError("not found")) is False


class TestIterHistoryChanges:
    def test_yields_history_records(self) -> None:
        service = MagicMock()
        record = {"id": "H1", "messagesAdded": [{"message": {"id": "new_msg"}}]}
        resp = {"history": [record]}
        service.users().history().list.return_value.execute.return_value = resp
        service.users().history().list_next.return_value = None

        records = list(iter_history_changes(service, "1000"))
        assert len(records) == 1
        assert records[0]["id"] == "H1"

    def test_raises_history_expired_on_404(self) -> None:
        from googleapiclient.errors import HttpError

        service = MagicMock()
        fake_resp = MagicMock()
        fake_resp.status = 404
        service.users().history().list.return_value.execute.side_effect = HttpError(
            resp=fake_resp, content=b"Gone"
        )

        with pytest.raises(HistoryExpiredError):
            list(iter_history_changes(service, "expired_id"))

    def test_empty_history(self) -> None:
        service = MagicMock()
        service.users().history().list.return_value.execute.return_value = {}
        service.users().history().list_next.return_value = None

        records = list(iter_history_changes(service, "1000"))
        assert records == []


# ─── runner integration ───────────────────────────────────────────────────────


class TestRunIngest:
    """Integration tests for run_ingest() with mocked Gmail service and DB."""

    def _build_service(
        self,
        message_ids: list[str],
        api_responses: dict[str, Any] | None = None,
        profile_history_id: str = "99999",
    ) -> MagicMock:
        service = MagicMock()

        # getProfile
        service.users().getProfile.return_value.execute.return_value = {
            "historyId": profile_history_id
        }

        # messages.list (single page)
        list_resp = _make_list_response(message_ids)
        service.users().messages().list.return_value.execute.return_value = list_resp
        service.users().messages().list_next.return_value = None

        # batch
        if api_responses is None:
            api_responses = {mid: _make_raw_api_response(mid) for mid in message_ids}

        def new_batch(callback):
            b = MagicMock()
            b._cb = callback
            b._added: list[str] = []

            def add(req, request_id: str):
                b._added.append(request_id)

            def execute():
                for rid in b._added:
                    if rid in api_responses:
                        b._cb(rid, api_responses[rid], None)
                    else:
                        b._cb(rid, None, Exception("missing"))

            b.add = add
            b.execute = execute
            return b

        service.new_batch_http_request.side_effect = new_batch
        return service

    def test_full_fetch_inserts_messages(
        self, app_config: AppConfig, tmp_data_dir: Path
    ) -> None:
        service = self._build_service(["m1", "m2", "m3"])

        with patch(
            "email_classifier.ingest.runner.get_gmail_service", return_value=service
        ):
            stats = run_ingest(app_config, force_full=True)

        assert stats.inserted == 3
        assert stats.updated == 0

        # Verify DB contents.
        with Database(app_config.ingest.db_path) as db:
            assert db.count_messages() == 3
            assert db.get_history_id() == "99999"

    def test_incremental_sync_new_message(
        self, app_config: AppConfig, tmp_data_dir: Path
    ) -> None:
        """After a full fetch, a new message in history should be inserted."""
        service = self._build_service(["m1"])

        # Seed the DB with an existing message + historyId.
        with Database(app_config.ingest.db_path) as db:
            db.upsert_message(
                "m1", "t1", 1_000_000, "10001",
                make_raw_email(), ["INBOX"], "a@x.com", "subj"
            )
            db.set_history_id("10001")

        # On incremental run, history returns one new message.
        history_resp = {
            "history": [{"id": "H2", "messagesAdded": [{"message": {"id": "m2"}}]}]
        }
        service.users().history().list.return_value.execute.return_value = history_resp
        service.users().history().list_next.return_value = None

        # Batch get for m2
        api_resps = {"m2": _make_raw_api_response("m2")}

        def new_batch(callback):
            b = MagicMock()
            b._cb = callback
            b._added: list[str] = []

            def add(req, request_id: str):
                b._added.append(request_id)

            def execute():
                for rid in b._added:
                    if rid in api_resps:
                        b._cb(rid, api_resps[rid], None)
                    else:
                        b._cb(rid, None, Exception("missing"))

            b.add = add
            b.execute = execute
            return b

        service.new_batch_http_request.side_effect = new_batch

        with patch(
            "email_classifier.ingest.runner.get_gmail_service", return_value=service
        ):
            stats = run_ingest(app_config)

        # m2 should be inserted; m1 was not touched.
        assert stats.inserted == 1

    def test_backfill_missing_after_incremental(
        self, app_config: AppConfig, tmp_data_dir: Path
    ) -> None:
        """Older mail missing from SQLite is fetched even when history is empty."""
        service = self._build_service(["m1", "m_gap"])
        with Database(app_config.ingest.db_path) as db:
            db.upsert_message(
                "m1", "t1", 1_000_000, "10001",
                make_raw_email(), ["INBOX"], "a@x.com", "subj"
            )
            db.set_history_id("10001")

        service.users().history().list.return_value.execute.return_value = {}
        service.users().history().list_next.return_value = None
        api_resps = {"m_gap": _make_raw_api_response("m_gap")}

        def new_batch(callback):
            b = MagicMock()
            b._cb = callback
            b._added: list[str] = []

            def add(req, request_id: str):
                b._added.append(request_id)

            def execute():
                for rid in b._added:
                    if rid in api_resps:
                        b._cb(rid, api_resps[rid], None)
                    else:
                        b._cb(rid, None, Exception("missing"))

            b.add = add
            b.execute = execute
            return b

        service.new_batch_http_request.side_effect = new_batch

        with patch(
            "email_classifier.ingest.runner.get_gmail_service", return_value=service
        ):
            stats = run_ingest(app_config)

        assert stats.inserted == 1
        with Database(app_config.ingest.db_path) as db:
            assert db.message_exists("m_gap")

    def test_expired_history_falls_back_to_full(
        self, app_config: AppConfig, tmp_data_dir: Path
    ) -> None:
        """A 404 from history.list should trigger a full fetch."""
        from googleapiclient.errors import HttpError

        service = self._build_service(["m1"])

        # Seed a historyId so incremental path is chosen.
        with Database(app_config.ingest.db_path) as db:
            db.set_history_id("old_id")

        fake_resp = MagicMock()
        fake_resp.status = 404
        service.users().history().list.return_value.execute.side_effect = HttpError(
            resp=fake_resp, content=b"Gone"
        )

        with patch(
            "email_classifier.ingest.runner.get_gmail_service", return_value=service
        ):
            stats = run_ingest(app_config)

        # Should have fallen back and inserted m1.
        assert stats.inserted == 1

    def test_promotions_as_ignore_skips_messages(
        self, app_config: AppConfig, tmp_data_dir: Path
    ) -> None:
        app_config.ingest.promotions_as = "ignore"
        promo_resp = _make_raw_api_response("m_promo", label_ids=["CATEGORY_PROMOTIONS"])
        service = self._build_service(["m_promo"], api_responses={"m_promo": promo_resp})

        with patch(
            "email_classifier.ingest.runner.get_gmail_service", return_value=service
        ):
            stats = run_ingest(app_config, force_full=True)

        assert stats.inserted == 0
        assert stats.skipped == 1

    def test_spam_messages_counted(
        self, app_config: AppConfig, tmp_data_dir: Path
    ) -> None:
        spam_resp = _make_raw_api_response("m_spam", label_ids=["SPAM"])
        service = self._build_service(["m_spam"], api_responses={"m_spam": spam_resp})

        with patch(
            "email_classifier.ingest.runner.get_gmail_service", return_value=service
        ):
            stats = run_ingest(app_config, force_full=True)

        assert stats.spam == 1
        assert stats.ham == 0

    def test_history_id_saved_after_ingest(
        self, app_config: AppConfig, tmp_data_dir: Path
    ) -> None:
        service = self._build_service([], profile_history_id="12345")
        # Empty mailbox.
        service.users().messages().list.return_value.execute.return_value = {}
        service.users().messages().list_next.return_value = None

        with patch(
            "email_classifier.ingest.runner.get_gmail_service", return_value=service
        ):
            stats = run_ingest(app_config, force_full=True)

        with Database(app_config.ingest.db_path) as db:
            assert db.get_history_id() == "12345"

    def test_force_full_resets_incremental(
        self, app_config: AppConfig, tmp_data_dir: Path
    ) -> None:
        """force_full=True should call messages.list, not history.list."""
        with Database(app_config.ingest.db_path) as db:
            db.set_history_id("old_id")

        service = self._build_service(["m1"])

        with patch(
            "email_classifier.ingest.runner.get_gmail_service", return_value=service
        ):
            run_ingest(app_config, force_full=True)

        # history.list should NOT have been called.
        service.users().history().list.assert_not_called()
