"""Code-computed email signals: auth headers, link domains, identity checks."""

from email_classifier.features.auth import AuthResults, parse_auth_results
from email_classifier.features.identity import from_reply_to_mismatch
from email_classifier.features.links import dedupe_link_domains, domain_from_url

__all__ = [
    "AuthResults",
    "parse_auth_results",
    "from_reply_to_mismatch",
    "dedupe_link_domains",
    "domain_from_url",
]
