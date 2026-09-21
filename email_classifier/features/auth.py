"""Parse SPF / DKIM / DMARC results from email authentication headers.

These values are computed in Python and passed into Jev state. Jev is never
asked to parse headers.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

_RESULT_RE = re.compile(
    r"\b(spf|dkim|dmarc)\s*=\s*([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
_RECEIVED_SPF_RE = re.compile(r"^\s*([a-zA-Z0-9_-]+)", re.IGNORECASE)

_KNOWN = frozenset(
    {"pass", "fail", "softfail", "neutral", "none", "temperror", "permerror"}
)


class AuthResults(BaseModel):
    spf_result: str = "none"
    dkim_result: str = "none"
    dmarc_result: str = "none"


def _normalize(value: str) -> str:
    v = value.strip().lower()
    return v if v in _KNOWN else v or "none"


def parse_auth_results(
    authentication_results: str = "",
    received_spf: str = "",
) -> AuthResults:
    """Extract SPF/DKIM/DMARC from Authentication-Results and Received-SPF."""
    found: dict[str, str] = {}
    for match in _RESULT_RE.finditer(authentication_results or ""):
        key = match.group(1).lower()
        # First occurrence wins (the outermost receiver's verdict).
        if key not in found:
            found[key] = _normalize(match.group(2))

    spf = found.get("spf", "none")
    if spf == "none" and received_spf:
        m = _RECEIVED_SPF_RE.match(received_spf)
        if m:
            spf = _normalize(m.group(1))

    return AuthResults(
        spf_result=spf,
        dkim_result=found.get("dkim", "none"),
        dmarc_result=found.get("dmarc", "none"),
    )
