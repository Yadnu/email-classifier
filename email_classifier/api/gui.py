"""GUI inspect APIs under /api. Bound for local use; CORS is 127.0.0.1 only."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from email_classifier.api.compact import compact_row, gmail_spam
from email_classifier.api.live import sse_lines, subscribe, unsubscribe
from email_classifier.config import load_config
from email_classifier.decide.explain import decision_trail, explain_verdict
from email_classifier.eval.metrics import calibration_table, percentiles
from email_classifier.eval.stats import parse_date
from email_classifier.ingest.db import Database
from email_classifier.jev.client import JevClient
from email_classifier.jev.snapshot import snapshot_questions
from email_classifier.jev.state import BuiltState, JevState, build_state
from email_classifier.models.result import ClassificationResult
from email_classifier.observability.spans import span_tree_from_result
from email_classifier.parse.mime import parse_raw
from email_classifier.pipeline import _ms, _timings, build_result

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
    if bucket not in {"hour", "day"}:
        raise HTTPException(status_code=400, detail="bucket must be hour or day")
    db = _db()
    try:
        rows = db.classifications_in_range(_start_iso(from_date), _end_iso(to_date))
        cats: dict[str, int] = {}
        totals: list[float] = []
        jevs: list[float] = []
        costs: list[float] = []
        tokens = 0
        confidences: list[float] = []
        uncertain = 0
        errors = 0
        limited = 0
        retries = 0
        agree = 0
        labeled = 0
        hist = [0] * 10
        series: dict[str, dict[str, int]] = {}
        for row in rows:
            result = ClassificationResult.model_validate_json(row["result_json"])
            cats[result.category] = cats.get(result.category, 0) + 1
            totals.append(float(result.classification_time_ms.total))
            jevs.append(float(result.classification_time_ms.jev_call))
            costs.append(result.observability.cost_usd)
            tokens += result.observability.input_tokens
            confidences.append(result.category_confidence)
            if result.category == "uncertain":
                uncertain += 1
            if result.observability.decision_path == "jev_error":
                errors += 1
            if result.observability.rate_limited:
                limited += 1
            retries += result.observability.retries
            labeled += 1
            if gmail_spam(row["label_ids"]) == result.spam:
                agree += 1
            idx = min(int(result.category_confidence * 10), 9)
            hist[idx] += 1
            key = row["classified_at"][:13] if bucket == "hour" else row["classified_at"][:10]
            bucket_counts = series.setdefault(key, {})
            bucket_counts[result.category] = bucket_counts.get(result.category, 0) + 1
        n = len(rows)
        return {
            "n": n,
            "counts_by_category": cats,
            "latency": {
                "total": percentiles(totals),
                "jev_call": percentiles(jevs),
            },
            "cost_usd_total": sum(costs),
            "cost_usd_per_email": (sum(costs) / n) if n else 0.0,
            "input_tokens_total": tokens,
            "confidence_histogram": [
                {"lo": i / 10, "hi": (i + 1) / 10, "n": hist[i]} for i in range(10)
            ],
            "uncertain_rate": (uncertain / n) if n else 0.0,
            "errors": errors,
            "rate_limited": limited,
            "retries": retries,
            "gmail_agreement": (agree / labeled) if labeled else 0.0,
            "volume": [{"bucket": k, "counts": v} for k, v in sorted(series.items())],
        }
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
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
