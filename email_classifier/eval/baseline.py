"""Rule baseline: SPF/DKIM failure or From vs Reply-To mismatch → spam."""
from __future__ import annotations

from email_classifier.features.auth import parse_auth_results
from email_classifier.features.identity import from_reply_to_mismatch
from email_classifier.parse.mime import parse_raw

_FAIL = frozenset({"fail", "softfail"})


def baseline_predicts_spam(raw_rfc822: bytes) -> bool:
    """True when auth headers fail or From domain ≠ Reply-To domain."""
    parsed = parse_raw(raw_rfc822)
    auth = parse_auth_results(
        parsed.authentication_results,
        parsed.received_spf,
    )
    if auth.spf_result in _FAIL or auth.dkim_result in _FAIL:
        return True
    return from_reply_to_mismatch(parsed.sender_domain, parsed.reply_to_domain)
