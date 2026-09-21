"""Gmail API helpers: paginated list, batch RAW get, and history sync.

All network calls use the authenticated service built by
``email_classifier.auth.get_gmail_service``.

Key design decisions
--------------------
* ``messages.list`` with ``includeSpamTrash=True`` and pagination.
* ``messages.get(format='raw')`` via Gmail's batch HTTP endpoint (up to 50)
  per batch) to reduce round-trips.
* Incremental sync via ``users.history.list(startHistoryId=...)``; a 404
  (history expired) falls back to a full list.
* Subjects and email addresses are never printed or logged — only counts.
"""
from __future__ import annotations

import base64
import email as stdlib_email
import json
import time
from typing import Any, Callable, Generator, Iterator, Optional

import httplib2
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest

# Gmail limits batch requests to 50 items.
_MAX_BATCH = 50
_RATE_REASONS = ("ratelimitexceeded", "userratelimitexceeded", "quotaexceeded")


def _is_rate_limit(exc: BaseException) -> bool:
    """True for Gmail HTTP 429 / 403 quota errors."""
    if isinstance(exc, HttpError):
        if exc.resp is not None and exc.resp.status in {403, 429}:
            body = (exc.content or b"").decode("utf-8", errors="replace").lower()
            if any(r in body for r in _RATE_REASONS) or exc.resp.status == 429:
                return True
    text = str(exc).lower()
    return any(r in text for r in _RATE_REASONS) or "rate limit" in text


def _sleep_backoff(attempt: int, base: float = 2.0) -> None:
    # 2, 4, 8, 16, 32, 60 seconds
    delay = min(60.0, base * (2**attempt))
    print(f"  [rate limit] waiting {delay:.0f}s then retrying …")
    time.sleep(delay)


# ─── list helpers ─────────────────────────────────────────────────────────────


def iter_message_ids(
    service: Resource,
    page_size: int = 500,
    include_spam_trash: bool = True,
    max_messages: Optional[int] = None,
) -> Generator[str, None, None]:
    """Yield every message ID in the mailbox.

    Parameters
    ----------
    service:
        Authenticated Gmail service resource.
    page_size:
        Number of results per page (1–500).
    include_spam_trash:
        Include Spam and Trash folders.
    max_messages:
        Stop after yielding this many IDs (safety cap).
    """
    yielded = 0
    request = service.users().messages().list(
        userId="me",
        maxResults=min(page_size, 500),
        includeSpamTrash=include_spam_trash,
    )
    while request is not None:
        response: dict[str, Any] = request.execute()
        for msg in response.get("messages", []):
            yield msg["id"]
            yielded += 1
            if max_messages is not None and yielded >= max_messages:
                return
        request = (
            service.users()
            .messages()
            .list_next(previous_request=request, previous_response=response)
        )


# ─── batch RAW get ────────────────────────────────────────────────────────────


def _parse_raw_headers(raw_bytes: bytes) -> tuple[Optional[str], Optional[str]]:
    """Return (from_header, subject) from raw RFC 5322 bytes."""
    try:
        msg = stdlib_email.message_from_bytes(raw_bytes)
        return msg.get("From"), msg.get("Subject")
    except Exception:
        return None, None


def _decode_gmail_raw(msg_id: str, resp: dict[str, Any]) -> dict[str, Any]:
    raw_b64 = resp.get("raw", "")
    raw_bytes = base64.urlsafe_b64decode(raw_b64 + "==")
    from_header, subject = _parse_raw_headers(raw_bytes)
    return {
        "id": resp.get("id", msg_id),
        "threadId": resp.get("threadId", ""),
        "labelIds": resp.get("labelIds", []),
        "internalDate": int(resp.get("internalDate", 0)),
        "historyId": resp.get("historyId"),
        "raw_bytes": raw_bytes,
        "from_header": from_header,
        "subject": subject,
    }


def _execute_batch(
    service: Resource,
    chunk: list[str],
    max_retries: int,
) -> dict[str, Any]:
    """Run one Gmail batch, retrying the whole chunk on rate limits."""
    results: dict[str, Any] = {}
    pending = list(chunk)

    for attempt in range(max_retries + 1):
        results.clear()
        rate_limited_ids: list[str] = []

        def _callback(
            request_id: str,
            response: Optional[dict],
            exception: Optional[Exception],
        ) -> None:
            if exception:
                if _is_rate_limit(exception):
                    rate_limited_ids.append(request_id)
                    return
                print(f"  [warn] batch get failed for {request_id}: {exception}")
                return
            if response:
                results[request_id] = response

        batch: BatchHttpRequest = service.new_batch_http_request(callback=_callback)
        for msg_id in pending:
            batch.add(
                service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="raw",
                ),
                request_id=msg_id,
            )
        try:
            batch.execute()
        except Exception as exc:
            if _is_rate_limit(exc) and attempt < max_retries:
                _sleep_backoff(attempt)
                continue
            raise

        if not rate_limited_ids:
            return results
        pending = rate_limited_ids
        if attempt < max_retries:
            _sleep_backoff(attempt)
            continue
        print(
            f"  [warn] giving up on {len(pending)} message(s) after rate-limit retries"
        )
        return results

    return results


def batch_get_messages(
    service: Resource,
    message_ids: list[str],
    batch_size: int = 10,
    batch_pause_s: float = 0.0,
    max_retries: int = 6,
) -> Generator[dict[str, Any], None, None]:
    """Yield full message dicts (raw format) for each message ID.

    Uses Gmail's batch HTTP endpoint so each chunk of ``batch_size`` messages
    counts as a single HTTP round-trip. Rate limits are retried with backoff.

    Yielded dict keys
    -----------------
    id, threadId, labelIds, internalDate, historyId, raw_bytes (bytes),
    from_header (str | None), subject (str | None)
    """
    ids = list(message_ids)
    size = min(max(1, batch_size), _MAX_BATCH)
    for chunk_start in range(0, len(ids), size):
        if chunk_start > 0 and batch_pause_s > 0:
            time.sleep(batch_pause_s)
        chunk = ids[chunk_start : chunk_start + size]
        results = _execute_batch(service, chunk, max_retries=max_retries)
        for msg_id in chunk:
            if msg_id not in results:
                continue
            yield _decode_gmail_raw(msg_id, results[msg_id])


# ─── incremental history sync ─────────────────────────────────────────────────


class HistoryExpiredError(Exception):
    """Raised when Gmail returns 404 for a historyId (history window expired)."""


def iter_history_changes(
    service: Resource,
    start_history_id: str,
    page_size: int = 500,
    max_messages: Optional[int] = None,
) -> Generator[dict[str, Any], None, None]:
    """Yield history records since ``start_history_id``.

    Each record is a Gmail history resource dict which may contain
    ``messagesAdded``, ``messagesDeleted``, ``labelsAdded``, ``labelsRemoved``.

    Raises
    ------
    HistoryExpiredError
        If Gmail returns HTTP 404, meaning the history window has expired.
        The caller should fall back to a full list sync.
    """
    yielded = 0
    request = service.users().history().list(
        userId="me",
        startHistoryId=start_history_id,
        maxResults=min(page_size, 500),
        historyTypes=["messageAdded", "messageDeleted", "labelAdded", "labelRemoved"],
    )
    while request is not None:
        try:
            response: dict[str, Any] = request.execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                raise HistoryExpiredError(
                    f"historyId {start_history_id} has expired"
                ) from exc
            raise

        for record in response.get("history", []):
            yield record
            yielded += 1
            if max_messages is not None and yielded >= max_messages:
                return

        request = (
            service.users()
            .history()
            .list_next(previous_request=request, previous_response=response)
        )


def get_profile(service: Resource) -> dict[str, Any]:
    """Return the Gmail profile dict, which includes the current historyId."""
    return service.users().getProfile(userId="me").execute()


def get_message(service: Resource, message_id: str, max_retries: int = 6) -> dict[str, Any]:
    """Fetch a single message in RAW format and return the enriched dict."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            resp = service.users().messages().get(
                userId="me", id=message_id, format="raw"
            ).execute()
            break
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit(exc) and attempt < max_retries:
                _sleep_backoff(attempt)
                continue
            raise
    else:
        raise last_exc if last_exc else RuntimeError("get_message failed")
    raw_b64 = resp.get("raw", "")
    raw_bytes = base64.urlsafe_b64decode(raw_b64 + "==")
    from_header, subject = _parse_raw_headers(raw_bytes)
    return {
        "id": resp.get("id", message_id),
        "threadId": resp.get("threadId", ""),
        "labelIds": resp.get("labelIds", []),
        "internalDate": int(resp.get("internalDate", 0)),
        "historyId": resp.get("historyId"),
        "raw_bytes": raw_bytes,
        "from_header": from_header,
        "subject": subject,
    }
