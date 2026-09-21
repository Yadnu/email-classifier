"""GUI inspect APIs under /api. Bound for local use; CORS is 127.0.0.1 only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from email_classifier.api.compact import compact_row, gmail_spam
from email_classifier.api.live import sse_lines, subscribe, unsubscribe
from email_classifier.api.stats_build import build_stats
from email_classifier.api.thresholds_io import (
    THRESHOLD_KEYS,
    config_path,
    read_thresholds,
    write_thresholds,
)
from email_classifier.config import load_config
from email_classifier.decide.explain import decision_trail, explain_verdict
from email_classifier.eval.metrics import calibration_table
from email_classifier.eval.stats import parse_date
from email_classifier.ingest.db import Database
from email_classifier.ingest.runner import IngestStats, run_ingest
from email_classifier.jev.client import JevClient
from email_classifier.jev.snapshot import snapshot_questions
from email_classifier.jev.state import BuiltState, JevState, build_state
from email_classifier.models.result import ClassificationResult
from email_classifier.observability.spans import span_tree_from_result
from email_classifier.parse.mime import parse_raw
from email_classifier.pipeline import _ms, _timings, build_result, classify_message as run_classify

router = APIRouter(prefix="/api")


def _db() -> Database:
    cfg = load_config()
    db = Database(cfg.ingest.db_path)
    db.open()
    return db


def _end_iso(to_date: Optional[str]) -> Optional[str]:
    dt = parse_date(to_date, end_of_day=True)
    return dt.isoformat() if dt else None


def _start_iso(from_date: Optional[str]) -> Optional[str]:
    dt = parse_date(from_date)
    return dt.isoformat() if dt else None


def _parse_cursor(cursor: Optional[str]) -> tuple[Optional[str], Optional[int]]:
    if not cursor:
        return None, None
    if "|" not in cursor:
        raise HTTPException(status_code=400, detail="cursor must be classified_at|id")
    at, _, raw_id = cursor.partition("|")
    try:
        return at, int(raw_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor id") from exc


def _questions_with_answers(
    questions: list[dict[str, Any]],
    result: ClassificationResult,
    answers: Optional[dict[str, Any]],
) -> list[dict[str, Any]]:
    ans = answers or {}
    cards: list[dict[str, Any]] = []
    for q in questions:
        card = dict(q)
        name = q.get("name")
        qtype = q.get("type")
        if qtype == "Choice" and name == "category":
            card["answer"] = {
                "choice": result.category if result.category != "uncertain" else ans.get("category", result.category),
                "confidence": result.category_confidence,
                "probabilities": result.category_probabilities,
            }
        elif qtype == "Noul":
            mapping = {
                "is_spam": result.spam_probability,
                "needs_reply": result.reply_probability,
                "credential_request": result.signals.credential_request,
                "brand_impersonation": result.signals.brand_impersonation,
            }
            card["answer"] = {"noul": mapping.get(name, ans.get(name))}
        elif qtype == "Score" and name == "pressure":
            card["answer"] = {"score": result.signals.pressure_score}
        cards.append(card)
    return cards


def _reconstruct_trace(row, result: ClassificationResult) -> tuple[dict, list, dict, dict]:
    cfg = load_config()
    questions = snapshot_questions()
    spans = span_tree_from_result(result)
    state: dict[str, Any] = {}
    raw = row["raw_rfc822"]
    if raw:
        if isinstance(raw, memoryview):
            raw = raw.tobytes()
        parsed = parse_raw(bytes(raw))
        built = build_state(parsed, cfg.jev.body_excerpt_chars)
        state = built.state.to_payload()
    answers = {
        "category": result.category,
        "category_confidence": result.category_confidence,
        "category_probabilities": result.category_probabilities,
        "is_spam": result.spam_probability,
        "needs_reply": result.reply_probability,
        "credential_request": result.signals.credential_request,
        "brand_impersonation": result.signals.brand_impersonation,
        "pressure_score": result.signals.pressure_score,
    }
    return state, questions, spans, answers


@router.get("/messages")
def list_messages(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    category: Optional[str] = None,
    min_confidence: Optional[float] = None,
    search: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    try:
        if from_date:
            parse_date(from_date)
        if to_date:
            parse_date(to_date, end_of_day=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="from/to must be YYYY-MM-DD") from exc
    before_at, before_id = _parse_cursor(cursor)
    db = _db()
    try:
        rows = db.list_latest_classified(
            start_iso=_start_iso(from_date),
            end_iso=_end_iso(to_date),
            category=category,
            min_confidence=min_confidence,
            search=search,
            before_at=before_at,
            before_id=before_id,
            limit=limit + 1,
        )
        page = rows[:limit]
        items = []
        for row in page:
            result = ClassificationResult.model_validate_json(row["result_json"])
            items.append(
                compact_row(
                    message_id=row["message_id"],
                    classified_at=row["classified_at"],
                    classification_id=row["id"],
                    result=result,
                    from_header=row["from_header"],
                    subject=row["subject"],
                    label_ids_json=row["label_ids"],
                )
            )
        next_cursor = None
        if len(rows) > limit:
            last = page[-1]
            next_cursor = f"{last['classified_at']}|{last['id']}"
        return {"items": items, "next_cursor": next_cursor}
    finally:
        db.close()


@router.get("/messages/{message_id}")
def get_message(message_id: str) -> dict[str, Any]:
    cfg = load_config()
    db = _db()
    try:
        row = db.get_latest_classification(message_id)
        if row is None:
            raise HTTPException(status_code=404, detail="message not classified")
        result = ClassificationResult.model_validate_json(row["result_json"])
        if row["state_json"]:
            state = json.loads(row["state_json"])
            questions = json.loads(row["questions_json"] or "[]")
            spans = json.loads(row["spans_json"] or "{}")
            answers = json.loads(row["answers_json"] or "{}")
        else:
            state, questions, spans, answers = _reconstruct_trace(row, result)
        return {
            "result": result.model_dump(),
            "explanation": explain_verdict(result, cfg.thresholds),
            "decision_trail": decision_trail(result, cfg.thresholds),
            "state": state,
            "state_size_chars": len(json.dumps(state, ensure_ascii=False)) if state else 0,
            "body_truncated": result.observability.body_truncated,
            "questions": _questions_with_answers(questions or snapshot_questions(), result, answers),
            "spans": spans or span_tree_from_result(result),
            "gmail_spam": gmail_spam(row["label_ids"]),
            "from_header": row["from_header"],
            "subject": row["subject"],
        }
    finally:
        db.close()


@router.get("/stats")
def stats(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    bucket: str = Query("hour"),
) -> dict[str, Any]:
    if bucket not in {"minute", "hour", "day"}:
        raise HTTPException(status_code=400, detail="bucket must be minute, hour, or day")
    db = _db()
    try:
        rows = db.classifications_in_range(_start_iso(from_date), _end_iso(to_date))
        return build_stats(rows, bucket)
    finally:
        db.close()


@router.get("/calibration")
def calibration(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
) -> dict[str, Any]:
    db = _db()
    try:
        rows = db.classifications_in_range(_start_iso(from_date), _end_iso(to_date))
        spam_p: list[float] = []
        spam_a: list[bool] = []
        reply_p: list[float] = []
        reply_a: list[bool] = []
        from email_classifier.ingest.ground_truth import is_replied_in_thread

        sent_cache: dict[str, list] = {}
        for row in rows:
            result = ClassificationResult.model_validate_json(row["result_json"])
            spam_p.append(result.spam_probability)
            spam_a.append(gmail_spam(row["label_ids"]))
            reply_p.append(result.reply_probability)
            full = db.get_message_row(row["message_id"])
            replied = False
            if full is not None:
                tid = full["thread_id"]
                if tid not in sent_cache:
                    sent_cache[tid] = db.get_thread_sent_dates(tid)
                replied = is_replied_in_thread(
                    row["message_id"], full["internal_date"], sent_cache[tid]
                )
            reply_a.append(replied)
        spam_bins = calibration_table(spam_p, spam_a)
        reply_bins = calibration_table(reply_p, reply_a)
        return {
            "spam": [b.__dict__ for b in spam_bins],
            "reply": [b.__dict__ for b in reply_bins],
        }
    finally:
        db.close()


@router.get("/live")
def live() -> StreamingResponse:
    q = subscribe()

    def gen():
        try:
            yield from sse_lines(q)
        finally:
            unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/replay/{message_id}")
def replay(message_id: str) -> dict[str, Any]:
    cfg = load_config()
    db = _db()
    try:
        row = db.get_latest_classification(message_id)
        if row is None:
            raise HTTPException(status_code=404, detail="message not classified")
        previous = ClassificationResult.model_validate_json(row["result_json"])
        if row["state_json"]:
            payload = json.loads(row["state_json"])
        else:
            payload, _, _, _ = _reconstruct_trace(row, previous)
        if not payload:
            raise HTTPException(status_code=400, detail="no stored state to replay")
        state = JevState.model_validate(payload)
        built = BuiltState(
            state=state,
            body_truncated=previous.observability.body_truncated,
            state_size_chars=len(json.dumps(payload, ensure_ascii=False)),
        )
        client = JevClient(model=cfg.jev.model)
        try:
            import time

            t0 = time.perf_counter()
            answers = client.classify_state(state.to_payload())
            jev_ms = answers.elapsed_ms or _ms(t0)
        finally:
            client.close()
        timings = _timings(jev_ms, 0, 0, 0, jev_ms, 0)
        replayed = build_result(message_id, answers, built, cfg, timings)
        fields = (
            "category",
            "category_confidence",
            "spam",
            "spam_probability",
            "reply_probability",
        )
        diff = {}
        for field in fields:
            old, new = getattr(previous, field), getattr(replayed, field)
            if old != new:
                diff[field] = {"from": old, "to": new}
        return {
            "previous": previous.model_dump(),
            "replayed": replayed.model_dump(),
            "diff": diff,
        }
    finally:
        db.close()


@router.get("/health")
def health() -> dict[str, Any]:
    from dotenv import load_dotenv

    load_dotenv()
    cfg = load_config()
    db = _db()
    try:
        token_expiry = None
        token_path = Path(cfg.gmail.token_path)
        if token_path.exists():
            try:
                token_expiry = json.loads(token_path.read_text()).get("expiry")
            except json.JSONDecodeError:
                token_expiry = None
        import os

        api_key = bool(os.environ.get("TYPESAFE_API_KEY"))
        return {
            "ok": True,
            "jev": {"api_key_present": api_key, "reachable": api_key},
            "gmail_token_expiry": token_expiry,
            "last_ingest_at": db.last_ingest_at(),
            "messages": db.count_messages(),
            "classifications": db.count_classifications(),
        }
    finally:
        db.close()


class SaveThresholdsBody(BaseModel):
    thresholds: dict[str, float]
    confirm: bool = False


class UpdateBody(BaseModel):
    classify_limit: int = 20


@router.post("/update")
def update_mailbox(body: UpdateBody | None = None) -> dict[str, Any]:
    """Sync Gmail into SQLite, then classify a batch of unclassified real mail.

    Counts only — never returns subjects or addresses. Ignores seed-* ids.
    """
    payload = body or UpdateBody()
    limit = payload.classify_limit
    if limit < 0 or limit > 50:
        raise HTTPException(status_code=400, detail="classify_limit must be 0–50")
    cfg = load_config()
    ingest_ok = True
    stats = IngestStats()
    try:
        stats = run_ingest(cfg)
    except Exception:
        ingest_ok = False

    classified = 0
    classify_failed = 0
    remaining = 0
    db = _db()
    try:
        for message_id in db.unclassified_message_ids(limit=limit):
            try:
                run_classify(message_id, cfg, db=db)
                classified += 1
            except Exception:
                classify_failed += 1
        remaining = db.count_unclassified()
    finally:
        db.close()

    return {
        "ingest_ok": ingest_ok,
        "ingested_new": stats.inserted,
        "ingested_updated": stats.updated,
        "ingested_fetched": stats.fetched,
        "ingest_complete": stats.complete,
        "classified": classified,
        "classify_failed": classify_failed,
        "unclassified_remaining": remaining,
    }


@router.get("/explorer")
def explorer(limit: int = Query(500, ge=1, le=2000)) -> dict[str, Any]:
    db = _db()
    try:
        rows = db.list_latest_classified(limit=limit)
        items = []
        for row in rows:
            result = ClassificationResult.model_validate_json(row["result_json"])
            items.append(
                compact_row(
                    message_id=row["message_id"],
                    classified_at=row["classified_at"],
                    classification_id=row["id"],
                    result=result,
                    from_header=row["from_header"],
                    subject=row["subject"],
                    label_ids_json=row["label_ids"],
                )
            )
        return {"items": items, "thresholds": read_thresholds()}
    finally:
        db.close()


@router.get("/thresholds")
def get_thresholds() -> dict[str, Any]:
    path = config_path()
    return {"path": str(path), "thresholds": read_thresholds()}


@router.post("/thresholds")
def save_thresholds(body: SaveThresholdsBody) -> dict[str, Any]:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="set confirm=true to write config.yaml")
    missing = [k for k in THRESHOLD_KEYS if k not in body.thresholds]
    extra = [k for k in body.thresholds if k not in THRESHOLD_KEYS]
    if missing or extra:
        raise HTTPException(
            status_code=400,
            detail=f"threshold keys must be exactly {list(THRESHOLD_KEYS)}",
        )
    try:
        written = write_thresholds(body.thresholds)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "path": str(config_path()), "thresholds": written}
