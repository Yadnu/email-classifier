"""End-to-end classify: fetch → parse → state → one Jev call → decide."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv

from email_classifier.config import AppConfig
from email_classifier.decide.logic import decide
from email_classifier.ingest.db import Database
from email_classifier.jev.client import JevAnswers, JevClient
from email_classifier.jev.state import BuiltState, build_state
from email_classifier.models.result import (
    ClassificationResult,
    ClassificationTimeMs,
    Observability,
    Signals,
    ThresholdsApplied,
)
from email_classifier.parse.mime import parse_raw

CATEGORY_KEYS = ("spam", "phishing", "promotional", "legitimate", "other")


def _ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _estimate_tokens(state_size_chars: int) -> int:
    return max(1, state_size_chars // 4)


def _normalize_probs(raw: dict[str, float]) -> dict[str, float]:
    return {k: float(raw.get(k, 0.0)) for k in CATEGORY_KEYS}


def _timings(
    total: int,
    gmail_fetch: int,
    parse: int,
    state_build: int,
    jev_call: int,
    decision: int,
) -> ClassificationTimeMs:
    parts = ClassificationTimeMs(
        total=total,
        gmail_fetch=gmail_fetch,
        parse=parse,
        state_build=state_build,
        jev_call=jev_call,
        decision=decision,
    )
    summed = (
        parts.gmail_fetch
        + parts.parse
        + parts.state_build
        + parts.jev_call
        + parts.decision
    )
    # Keep wall-clock total, but if overhead would break the ±5ms contract,
    # snap total to the sum (tests and CLI both need the breakdown to add up).
    if abs(parts.total - summed) > 5:
        parts = parts.model_copy(update={"total": summed})
    return parts


def _error_answers(elapsed_ms: int, retries: int, rate_limited: bool) -> JevAnswers:
    return JevAnswers(
        model="jev-1.13.0",
        category="other",
        category_confidence=0.0,
        category_probabilities={k: 0.0 for k in CATEGORY_KEYS},
        is_spam=0.0,
        needs_reply=0.0,
        credential_request=0.0,
        brand_impersonation=0.0,
        pressure_score=0.0,
        input_tokens=None,
        retries=retries,
        rate_limited=rate_limited,
        elapsed_ms=elapsed_ms,
    )


def _fetch_raw(
    message_id: str,
    cfg: AppConfig,
    db: Database,
    gmail_service: Any,
) -> tuple[bytes, int]:
    """Load RAW bytes from SQLite or Gmail. Returns (raw, gmail_fetch_ms)."""
    started = time.perf_counter()
    row = db.get_message_row(message_id)
    if row is not None and row["raw_rfc822"]:
        raw = row["raw_rfc822"]
        if isinstance(raw, memoryview):
            raw = raw.tobytes()
        return bytes(raw), 0

    if gmail_service is None:
        from email_classifier.auth.oauth import get_gmail_service

        gmail_service = get_gmail_service(
            credentials_path=cfg.gmail.credentials_path,
            token_path=cfg.gmail.token_path,
            scopes=cfg.gmail.readonly_scopes,
        )
    from email_classifier.ingest.gmail import get_message

    msg = get_message(gmail_service, message_id)
    db.upsert_message(
        message_id=msg["id"],
        thread_id=msg["threadId"],
        internal_date=msg["internalDate"],
        history_id=msg.get("historyId"),
        raw_rfc822=msg["raw_bytes"],
        label_ids=msg["labelIds"],
        from_header=msg.get("from_header"),
        subject=msg.get("subject"),
    )
    return msg["raw_bytes"], _ms(started)


def build_result(
    message_id: str,
    answers: JevAnswers,
    built: BuiltState,
    cfg: AppConfig,
    timings: ClassificationTimeMs,
    *,
    request_id: Optional[str] = None,
    decision_path_override: Optional[str] = None,
) -> ClassificationResult:
    request_id = request_id or str(uuid.uuid4())
    decision = decide(answers, cfg.thresholds)
    path = decision_path_override or decision.decision_path

    tokens_estimated = answers.input_tokens is None
    tokens = (
        answers.input_tokens
        if answers.input_tokens is not None
        else _estimate_tokens(built.state_size_chars)
    )
    cost = tokens / 1_000_000.0 * cfg.jev.price_per_million_input_tokens
    probs = _normalize_probs(answers.category_probabilities)

    return ClassificationResult(
        message_id=message_id,
        category=decision.category,
        category_confidence=decision.category_confidence,
        category_probabilities=probs,
        spam=decision.spam,
        spam_probability=answers.is_spam,
        reply_probability=answers.needs_reply,
        signals=Signals(
            credential_request=answers.credential_request,
            brand_impersonation=answers.brand_impersonation,
            pressure_score=answers.pressure_score,
        ),
        classification_time_ms=timings,
        observability=Observability(
            request_id=request_id,
            trace_id=request_id.replace("-", ""),
            model_version=answers.model,
            input_tokens=tokens,
            input_tokens_estimated=tokens_estimated,
            cost_usd=cost,
            state_size_chars=built.state_size_chars,
            body_truncated=built.body_truncated,
            retries=answers.retries,
            rate_limited=answers.rate_limited,
            thresholds_applied=ThresholdsApplied(
                spam=cfg.thresholds.spam_is_spam,
                phishing=cfg.thresholds.phishing_category_confidence,
                uncertain_floor=cfg.thresholds.uncertain_floor,
            ),
            decision_path=path,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
    )


def classify_message(
    message_id: str,
    cfg: AppConfig,
    *,
    jev_client: Optional[JevClient] = None,
    db: Optional[Database] = None,
    gmail_service: Any = None,
    persist: bool = True,
) -> ClassificationResult:
    """Classify one message. ``jev_client`` is injected in tests."""
    load_dotenv()
    wall = time.perf_counter()
    request_id = str(uuid.uuid4())
    owns_db = db is None
    if db is None:
        db = Database(cfg.ingest.db_path)
        db.open()

    try:
        raw, gmail_ms = _fetch_raw(message_id, cfg, db, gmail_service)

        t0 = time.perf_counter()
        parsed = parse_raw(raw)
        parse_ms = _ms(t0)

        t0 = time.perf_counter()
        built = build_state(parsed, cfg.jev.body_excerpt_chars)
        state_ms = _ms(t0)

        owns_client = jev_client is None
        if jev_client is None:
            jev_client = JevClient(model=cfg.jev.model)

        error_path: Optional[str] = None
        try:
            t0 = time.perf_counter()
            answers = jev_client.classify_state(built.state.to_payload())
            jev_ms = answers.elapsed_ms if answers.elapsed_ms else _ms(t0)
        except Exception:
            jev_ms = _ms(t0)
            retries = getattr(getattr(jev_client, "_counter", None), "retries", 0)
            rate_limited = getattr(
                getattr(jev_client, "_counter", None), "rate_limited", False
            )
            answers = _error_answers(jev_ms, retries, rate_limited)
            error_path = "jev_error"
        finally:
            if owns_client:
                jev_client.close()

        t0 = time.perf_counter()
        timings = _timings(
            total=_ms(wall),
            gmail_fetch=gmail_ms,
            parse=parse_ms,
            state_build=state_ms,
            jev_call=jev_ms,
            decision=0,
        )
        result = build_result(
            message_id,
            answers,
            built,
            cfg,
            timings,
            request_id=request_id,
            decision_path_override=error_path,
        )
        decision_ms = _ms(t0)
        result = result.model_copy(
            update={
                "classification_time_ms": _timings(
                    total=_ms(wall),
                    gmail_fetch=gmail_ms,
                    parse=parse_ms,
                    state_build=state_ms,
                    jev_call=jev_ms,
                    decision=decision_ms,
                )
            }
        )

        if persist:
            db.save_classification(
                message_id, result.model_dump_json()
            )
        return result
    finally:
        if owns_db:
            db.close()
