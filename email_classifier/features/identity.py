"""Identity checks that code can compute: From vs Reply-To domain mismatch."""
from __future__ import annotations


def from_reply_to_mismatch(sender_domain: str, reply_to_domain: str) -> bool:
    """True when Reply-To is present and its domain differs from From."""
    sender = (sender_domain or "").strip().lower()
    reply = (reply_to_domain or "").strip().lower()
    if not reply:
        return False
    return sender != reply
