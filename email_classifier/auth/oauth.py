"""Google OAuth 2.0 Desktop flow for Gmail API access.

Design rules
------------
* gmail.readonly is the default scope (ingest, classify).
* gmail.modify is requested separately only when label-inbox actually runs
  (Stage 6), using a distinct token file so the user can see what was granted.
* Missing credentials.json gives a friendly error that quotes the README setup
  steps rather than a raw FileNotFoundError stack trace.
* Token refresh is automatic; if the token is revoked the user is re-prompted.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

_MISSING_CREDS_MSG = """\
ERROR: Gmail credentials file not found at: {path}

To set up the Gmail API:
  1. Go to https://console.cloud.google.com and open (or create) a project.
  2. Enable the Gmail API:
       APIs & Services → Library → Gmail API → Enable
  3. Create a Desktop OAuth client:
       APIs & Services → Credentials → Create Credentials → OAuth client ID
       Application type: Desktop app
  4. Download the JSON file and save it as:
       {path}
  5. Add your Gmail address as a test user:
       APIs & Services → OAuth consent screen → Test users → Add Users

See README.md for full instructions.
"""


def get_credentials(
    credentials_path: str = "data/credentials.json",
    token_path: str = "data/token.json",
    scopes: Optional[list[str]] = None,
) -> Credentials:
    """Return valid Google credentials, running the OAuth flow if necessary.

    Parameters
    ----------
    credentials_path:
        Path to the Desktop OAuth client secrets JSON downloaded from Google
        Cloud Console.
    token_path:
        Where to persist / load the OAuth token. Created on first successful
        auth.
    scopes:
        OAuth scopes to request. Defaults to ``gmail.readonly``.

    Returns
    -------
    google.oauth2.credentials.Credentials
        Valid, possibly refreshed credentials.

    Raises
    ------
    SystemExit
        If ``credentials_path`` does not exist (with a human-friendly message).
    """
    if scopes is None:
        scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    creds_file = Path(credentials_path)
    if not creds_file.exists():
        sys.exit(_MISSING_CREDS_MSG.format(path=credentials_path))

    token_file = Path(token_path)
    creds: Optional[Credentials] = None

    # ── 1. Try to load a persisted token ────────────────────────────────────
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)

    # ── 2. Refresh or re-run the flow ────────────────────────────────────────
    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # Token revoked — fall through to re-run the flow.
            creds = None

    if creds is None:
        # Ensure data/ exists so the token write below succeeds.
        token_file.parent.mkdir(parents=True, exist_ok=True)

        flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), scopes)
        creds = flow.run_local_server(port=0, prompt="consent")

    # ── 3. Persist the refreshed / new token ─────────────────────────────────
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json())

    return creds


def get_gmail_service(
    credentials_path: str = "data/credentials.json",
    token_path: str = "data/token.json",
    scopes: Optional[list[str]] = None,
):
    """Build and return an authenticated Gmail API service resource.

    Parameters
    ----------
    credentials_path:
        Path to the Desktop OAuth client secrets JSON.
    token_path:
        Path to the persisted token JSON.
    scopes:
        OAuth scopes. Defaults to ``gmail.readonly``.

    Returns
    -------
    googleapiclient.discovery.Resource
        Authenticated ``gmail`` v1 service.
    """
    creds = get_credentials(
        credentials_path=credentials_path,
        token_path=token_path,
        scopes=scopes,
    )
    return build("gmail", "v1", credentials=creds)


def modify_token_path(token_path: str) -> str:
    """Sibling token file used only for gmail.modify (label-inbox)."""
    path = Path(token_path)
    return str(path.with_name(f"{path.stem}_modify{path.suffix}"))


def has_modify_scope(token_path: str = "data/token.json") -> bool:
    """Return True if the persisted token includes the gmail.modify scope."""
    token_file = Path(token_path)
    if not token_file.exists():
        return False
    creds = Credentials.from_authorized_user_file(str(token_file))
    granted = set(creds.scopes or [])
    return "https://www.googleapis.com/auth/gmail.modify" in granted
