"""OAuth Desktop flow for Gmail API."""

from email_classifier.auth.oauth import (
    get_credentials,
    get_gmail_service,
    has_modify_scope,
    modify_token_path,
)

__all__ = [
    "get_credentials",
    "get_gmail_service",
    "has_modify_scope",
    "modify_token_path",
]
