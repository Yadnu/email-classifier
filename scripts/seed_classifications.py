"""Generate realistic fake classifications for GUI development (no real mail, no Jev)."""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from email_classifier.config import load_config
from email_classifier.ingest.db import Database
from email_classifier.jev.snapshot import snapshot_questions
from email_classifier.models.result import (
    ClassificationResult,
    ClassificationTimeMs,
    Observability,
    Signals,
    ThresholdsApplied,
)
from email_classifier.observability.spans import span_tree_from_result

CATEGORIES = (
    "legitimate",
    "promotional",
    "spam",
    "phishing",
    "uncertain",
    "other",
)


def _raw(subject: str, from_addr: str, body: str) -> bytes:
    return (
        f"From: {from_addr}\r\n"
        f"Subject: {subject}\r\n"
        f"Authentication-Results: mx.google.com; spf=pass smtp.mailfrom=example.test\r\n"
        f"Content-Type: text/plain\r\n"
        f"\r\n"
        f"{body}\r\n"
    ).encode()


def _result(
    message_id: str,
    *,
    category: str,
    confidence: float,
    spam: bool,
    spam_p: float,
    reply_p: float,
    total_ms: int,
    jev_ms: int,
    cost: float,
    tokens: int,
    truncated: bool,
    retries: int,
    rate_limited: bool,
    path: str,
    timestamp: str,
) -> ClassificationResult:
    probs = {k: 0.02 for k in ("spam", "phishing", "promotional", "legitimate", "other")}
    if category in probs:
        probs[category] = max(confidence, 0.4)
    rest = max(0.0, 1.0 - sum(probs.values()))
    probs["other"] = round(probs["other"] + rest, 4)
    return ClassificationResult(
        message_id=message_id,
        category=category,  # type: ignore[arg-type]
        category_confidence=confidence,
        category_probabilities=probs,
        spam=spam,
        spam_probability=spam_p,
        reply_probability=reply_p,
        signals=Signals(
            credential_request=0.9 if category == "phishing" else 0.08,
            brand_impersonation=0.88 if category == "phishing" else 0.05,
            pressure_score=1.4 if category == "phishing" else 0.3,
        ),
        classification_time_ms=ClassificationTimeMs(
            total=total_ms,
            gmail_fetch=max(1, total_ms - jev_ms - 25),
            parse=8,
            state_build=6,
            jev_call=jev_ms,
            decision=4,
        ),
        observability=Observability(
            request_id=f"seed-{message_id}",
            trace_id="a" * 32,
            model_version="jev-1.13.0",
            input_tokens=tokens,
            input_tokens_estimated=False,
            cost_usd=cost,
            state_size_chars=400 + (800 if truncated else 0),
            body_truncated=truncated,
            retries=retries,
            rate_limited=rate_limited,
            thresholds_applied=ThresholdsApplied(
                spam=0.75, phishing=0.85, uncertain_floor=0.50
            ),
            decision_path=path,
            timestamp=timestamp,
        ),
    )


def seed(db_path: str, count: int, rng: random.Random) -> None:
    db = Database(db_path)
    db.open()
    questions = json.dumps(snapshot_questions())
    now = datetime.now(timezone.utc)
    try:
        for i in range(count):
            mid = f"seed-{i:04d}"
            cat = CATEGORIES[i % len(CATEGORIES)]
            if cat == "uncertain":
                conf, spam, spam_p, path = 0.32, False, 0.22, "uncertain_floor"
            elif cat == "spam":
                conf, spam, spam_p, path = 0.93, True, 0.91, "is_spam_noul"
            elif cat == "phishing":
                conf, spam, spam_p, path = 0.90, True, 0.84, "category_phishing"
            elif cat == "promotional":
                conf, spam, spam_p, path = 0.88, False, 0.18, "category_promotional"
            elif cat == "legitimate":
                conf, spam, spam_p, path = 0.86, False, 0.05, "category_legitimate"
            else:
                conf, spam, spam_p, path = 0.70, False, 0.11, "category_other"
            reply = 0.82 if cat == "legitimate" and i % 3 == 0 else rng.uniform(0.02, 0.25)
            jev_ms = rng.randint(180, 420)
            total_ms = jev_ms + rng.randint(20, 80)
            tokens = rng.randint(350, 1400)
            cost = tokens / 1_000_000.0 * 0.042
            when = now - timedelta(minutes=rng.randint(0, 60 * 24 * 5))
            ts = when.isoformat()
            labels = ["SPAM"] if (cat == "spam" and i % 5 != 0) or (cat == "legitimate" and i % 17 == 0) else ["INBOX"]
            subject = f"Seed subject {i} about {cat}"
            from_addr = f"user{i}@{cat}.example.test"
            result = _result(
                mid,
                category=cat,
                confidence=conf,
                spam=spam,
                spam_p=spam_p,
                reply_p=reply,
                total_ms=total_ms,
                jev_ms=jev_ms,
                cost=cost,
                tokens=tokens,
                truncated=i % 11 == 0,
                retries=1 if i % 13 == 0 else 0,
                rate_limited=i % 13 == 0,
                path=path,
                timestamp=ts,
            )
            # Snap timings to sum within 5ms.
            t = result.classification_time_ms
            summed = t.gmail_fetch + t.parse + t.state_build + t.jev_call + t.decision
            result = result.model_copy(
                update={"classification_time_ms": t.model_copy(update={"total": summed})}
            )
            db.upsert_message(
                mid,
                f"thread-{mid}",
                int(when.timestamp() * 1000),
                "seed",
                _raw(subject, from_addr, f"Body excerpt for {cat} message {i}."),
                labels,
                from_addr,
                subject,
            )
            state = {
                "sender_display_name": f"User {i}",
                "sender_address": from_addr,
                "sender_domain": from_addr.split("@", 1)[1],
                "reply_to_domain": from_addr.split("@", 1)[1],
                "subject": subject,
                "spf_result": "pass",
                "dkim_result": "pass",
                "dmarc_result": "pass",
                "link_domains": ["example.test"],
                "has_attachments": False,
                "body_excerpt": f"Body excerpt for {cat} message {i}.",
            }
            db.save_classification(
                mid,
                result.model_dump_json(),
                classified_at=ts,
                state_json=json.dumps(state),
                questions_json=questions,
                spans_json=json.dumps(span_tree_from_result(result)),
                answers_json=json.dumps(
                    {
                        "category": cat if cat != "uncertain" else "spam",
                        "category_confidence": conf,
                        "is_spam": spam_p,
                        "needs_reply": reply,
                    }
                ),
            )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="SQLite path (default: config.yaml ingest.db_path)")
    parser.add_argument("--count", type=int, default=80)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    db_path = args.db or load_config().ingest.db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    seed(db_path, args.count, random.Random(args.seed))
    print(f"Seeded {args.count} fake classifications into {db_path}")


if __name__ == "__main__":
    main()
