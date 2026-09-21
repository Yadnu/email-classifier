"""structlog JSON: one line per classification, never email content."""
from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

# Keys that must never appear in a log event (case-insensitive / substring).
_BLOCKED_EXACT = frozenset(
    {
        "subject",
        "from",
        "from_header",
        "from_addr",
        "sender_address",
        "sender_display_name",
        "sender_domain",
        "reply_to",
        "reply_to_domain",
        "address",
        "body",
        "body_excerpt",
        "raw",
        "raw_rfc822",
        "html",
        "text",
    }
)

_configured = False


def _drop_pii(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    for key in list(event_dict):
        if key.lower() in _BLOCKED_EXACT:
            event_dict.pop(key, None)
    return event_dict


def setup_logging(*, force: bool = False) -> None:
    global _configured
    if _configured and not force:
        return

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _drop_pii,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=lambda *args: structlog.PrintLogger(file=sys.stderr),
        cache_logger_on_first_use=False,
    )
    _configured = True


def log_classification(result) -> None:
    """Emit one JSON line. Observability + verdict fields only."""
    log = structlog.get_logger("email_classifier")
    obs = result.observability
    t = result.classification_time_ms
    log.info(
        "classification",
        request_id=obs.request_id,
        trace_id=obs.trace_id,
        message_id=result.message_id,
        category=result.category,
        category_confidence=result.category_confidence,
        spam=result.spam,
        spam_probability=result.spam_probability,
        reply_probability=result.reply_probability,
        decision_path=obs.decision_path,
        model_version=obs.model_version,
        input_tokens=obs.input_tokens,
        input_tokens_estimated=obs.input_tokens_estimated,
        cost_usd=obs.cost_usd,
        state_size_chars=obs.state_size_chars,
        body_truncated=obs.body_truncated,
        retries=obs.retries,
        rate_limited=obs.rate_limited,
        time_ms_total=t.total,
        time_ms_jev=t.jev_call,
    )
