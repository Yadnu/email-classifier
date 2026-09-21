"""Build the lean JSON state sent to Jev.

Jev loses accuracy when state has irrelevant material. This object contains
only the fields listed in the product contract. The body is always under the
explicit key ``body_excerpt`` so prompt-injection text cannot be confused
with instructions.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from email_classifier.features.auth import parse_auth_results
from email_classifier.features.identity import from_reply_to_mismatch
from email_classifier.features.links import dedupe_link_domains
from email_classifier.parse.mime import ParsedEmail


_STATE_KEYS = (
    "sender_display_name",
    "sender_address",
    "sender_domain",
    "reply_to_domain",
    "subject",
    "spf_result",
    "dkim_result",
    "dmarc_result",
    "link_domains",
    "has_attachments",
    "body_excerpt",
)


class JevState(BaseModel):
    """Exact state object passed to TypeSafeClient.system_one."""

    sender_display_name: str = ""
    sender_address: str = ""
    sender_domain: str = ""
    reply_to_domain: str = ""
    subject: str = ""
    spf_result: str = "none"
    dkim_result: str = "none"
    dmarc_result: str = "none"
    link_domains: list[str] = Field(default_factory=list)
    has_attachments: bool = False
    body_excerpt: str = ""

    def to_payload(self) -> dict[str, Any]:
        """JSON-serializable dict with only the allowed keys, in order."""
        return {key: getattr(self, key) for key in _STATE_KEYS}


class BuiltState(BaseModel):
    """State plus metadata used later for observability (not sent to Jev)."""

    state: JevState
    body_truncated: bool = False
    state_size_chars: int = 0
    link_count: int = 0
    from_reply_to_mismatch: bool = False


def _excerpt(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def build_state(parsed: ParsedEmail, body_excerpt_chars: int = 1500) -> BuiltState:
    """Assemble lean Jev state from a ParsedEmail."""
    auth = parse_auth_results(parsed.authentication_results, parsed.received_spf)
    link_domains = dedupe_link_domains(parsed.urls)
    excerpt, truncated = _excerpt(parsed.body_text, body_excerpt_chars)

    state = JevState(
        sender_display_name=parsed.sender_display_name,
        sender_address=parsed.sender_address,
        sender_domain=parsed.sender_domain,
        reply_to_domain=parsed.reply_to_domain,
        subject=parsed.subject,
        spf_result=auth.spf_result,
        dkim_result=auth.dkim_result,
        dmarc_result=auth.dmarc_result,
        link_domains=link_domains,
        has_attachments=parsed.has_attachments,
        body_excerpt=excerpt,
    )
    payload = state.to_payload()
    size = len(json.dumps(payload, ensure_ascii=False))
    return BuiltState(
        state=state,
        body_truncated=truncated,
        state_size_chars=size,
        link_count=len(parsed.urls),
        from_reply_to_mismatch=from_reply_to_mismatch(
            parsed.sender_domain, parsed.reply_to_domain
        ),
    )
