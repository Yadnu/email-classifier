"""Ground-truth label derivation from Gmail label IDs.

Rules (all computed in Python, no Jev involved)
------------------------------------------------
* SPAM in label_ids                          → "spam"
* INBOX or SENT present, SPAM absent        → "ham"
* CATEGORY_PROMOTIONS present, SPAM absent  → controlled by `promotions_as`
* A message is "replied" if a SENT message with a later internal_date exists
  in the same thread.

The promotions_as parameter mirrors config.yaml:
  "ignore"       → return None (caller should skip the message)
  "promotional"  → return "promotional"
  "ham"          → return "ham"
"""
from __future__ import annotations

from typing import Literal, Optional

GroundTruthLabel = Literal["spam", "ham", "promotional"]

_SPAM_LABEL = "SPAM"
_INBOX_LABEL = "INBOX"
_SENT_LABEL = "SENT"
_PROMOTIONS_LABEL = "CATEGORY_PROMOTIONS"


def label_for_message(
    label_ids: list[str],
    promotions_as: str = "promotional",
) -> Optional[GroundTruthLabel]:
    """Derive a ground-truth label from a list of Gmail label IDs.

    Parameters
    ----------
    label_ids:
        List of Gmail label ID strings from the API (e.g. ``["INBOX", "UNREAD"]``).
    promotions_as:
        How to handle messages with ``CATEGORY_PROMOTIONS`` but no ``SPAM``.
        ``"ignore"`` → return ``None`` (caller should skip).
        ``"promotional"`` → return ``"promotional"``.
        ``"ham"`` → return ``"ham"``.

    Returns
    -------
    GroundTruthLabel or None
        ``None`` means the message should be ignored (only when ``promotions_as``
        is ``"ignore"`` and the message is a promotion).
    """
    labels = set(label_ids)

    if _SPAM_LABEL in labels:
        return "spam"

    if _PROMOTIONS_LABEL in labels:
        if promotions_as == "ignore":
            return None
        if promotions_as == "promotional":
            return "promotional"
        # promotions_as == "ham"
        return "ham"

    if _INBOX_LABEL in labels or _SENT_LABEL in labels:
        return "ham"

    # Messages with no recognised label are left unlabeled (treated as ham for
    # ingest purposes — they landed in the inbox without SPAM or PROMOTIONS).
    return "ham"


def is_replied_in_thread(
    message_id: str,
    message_internal_date: Optional[int],
    thread_sent_pairs: list[tuple[str, int]],
) -> bool:
    """Return True if a SENT message exists in the thread after this message.

    Parameters
    ----------
    message_id:
        The message being evaluated.
    message_internal_date:
        Unix milliseconds timestamp of the message, from Gmail.
    thread_sent_pairs:
        List of (message_id, internal_date) for every SENT message in the same
        thread, ordered ascending by date.  Obtained via
        ``Database.get_thread_sent_dates``.

    Returns
    -------
    bool
        True if at least one SENT message has an internal_date strictly later
        than ``message_internal_date`` and a different ``message_id``.
    """
    if message_internal_date is None:
        return False

    for sent_id, sent_date in thread_sent_pairs:
        if sent_id != message_id and sent_date > message_internal_date:
            return True

    return False
