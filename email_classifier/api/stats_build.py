"""Build GET /api/stats payloads from classification rows."""
from __future__ import annotations

from typing import Any, Optional

from email_classifier.api.compact import gmail_spam
from email_classifier.eval.metrics import percentiles
from email_classifier.models.result import ClassificationResult

LATENCY_EDGES = (0, 100, 200, 300, 400, 500, 750, 1000, 2000, 5000)


def bucket_key(classified_at: str, bucket: str) -> str:
    if bucket == "day":
        return classified_at[:10]
    if bucket == "minute":
        return classified_at[:16]
    return classified_at[:13]


def _pct(values: list[float]) -> dict[str, float]:
    raw = percentiles(values)
    return {"50": raw[50], "95": raw[95], "99": raw[99]}


def latency_histogram(values: list[float]) -> list[dict[str, Any]]:
    last = len(LATENCY_EDGES) - 1
    counts = [0] * len(LATENCY_EDGES)
    for v in values:
        idx = last
        for j, hi in enumerate(LATENCY_EDGES[1:]):
            if v < hi:
                idx = j
                break
        counts[idx] += 1
    out = []
    for i, lo in enumerate(LATENCY_EDGES):
        hi: Optional[int] = LATENCY_EDGES[i + 1] if i + 1 < len(LATENCY_EDGES) else None
        out.append(
            {
                "lo": lo,
                "hi": hi,
                "n": counts[i],
                "label": f"{lo}+ ms" if hi is None else f"{lo}–{hi} ms",
            }
        )
    return out


def build_stats(rows, bucket: str) -> dict[str, Any]:
    cats: dict[str, int] = {}
    totals: list[float] = []
    jevs: list[float] = []
    costs: list[float] = []
    tokens = 0
    uncertain = 0
    errors = 0
    limited = 0
    retries = 0
    agree = 0
    labeled = 0
    conf_hist = [0] * 10
    buckets: dict[str, dict[str, Any]] = {}

    for row in rows:
        result = ClassificationResult.model_validate_json(row["result_json"])
        cats[result.category] = cats.get(result.category, 0) + 1
        total_ms = float(result.classification_time_ms.total)
        jev_ms = float(result.classification_time_ms.jev_call)
        totals.append(total_ms)
        jevs.append(jev_ms)
        costs.append(result.observability.cost_usd)
        tokens += result.observability.input_tokens
        if result.category == "uncertain":
            uncertain += 1
        if result.observability.decision_path == "jev_error":
            errors += 1
        if result.observability.rate_limited:
            limited += 1
        retries += result.observability.retries
        labeled += 1
        agreed = gmail_spam(row["label_ids"]) == result.spam
        if agreed:
            agree += 1
        idx = min(int(result.category_confidence * 10), 9)
        conf_hist[idx] += 1

        key = bucket_key(row["classified_at"], bucket)
        b = buckets.setdefault(
            key,
            {
                "totals": [],
                "jevs": [],
                "counts": {},
                "cost": 0.0,
                "tokens": 0,
                "uncertain": 0,
                "errors": 0,
                "rate_limited": 0,
                "retries": 0,
                "agree": 0,
                "n": 0,
            },
        )
        b["n"] += 1
        b["totals"].append(total_ms)
        b["jevs"].append(jev_ms)
        b["counts"][result.category] = b["counts"].get(result.category, 0) + 1
        b["cost"] += result.observability.cost_usd
        b["tokens"] += result.observability.input_tokens
        if result.category == "uncertain":
            b["uncertain"] += 1
        if result.observability.decision_path == "jev_error":
            b["errors"] += 1
        if result.observability.rate_limited:
            b["rate_limited"] += 1
        b["retries"] += result.observability.retries
        if agreed:
            b["agree"] += 1

    n = len(rows)
    cost_total = sum(costs)
    cost_per = (cost_total / n) if n else 0.0
    series = []
    running = 0.0
    for key in sorted(buckets):
        b = buckets[key]
        running += b["cost"]
        bn = b["n"]
        series.append(
            {
                "bucket": key,
                "n": bn,
                "counts": b["counts"],
                "latency_total": _pct(b["totals"]),
                "latency_jev": _pct(b["jevs"]),
                "cost_usd": b["cost"],
                "cost_usd_cumulative": running,
                "input_tokens": b["tokens"],
                "uncertain_n": b["uncertain"],
                "uncertain_rate": (b["uncertain"] / bn) if bn else 0.0,
                "errors": b["errors"],
                "rate_limited": b["rate_limited"],
                "retries": b["retries"],
                "gmail_agreement": (b["agree"] / bn) if bn else 0.0,
            }
        )

    return {
        "n": n,
        "counts_by_category": cats,
        "latency": {"total": _pct(totals), "jev_call": _pct(jevs)},
        "latency_histogram": latency_histogram(totals),
        "cost_usd_total": cost_total,
        "cost_usd_per_email": cost_per,
        "cost_usd_per_1000": cost_per * 1000.0,
        "projected_cost_usd": {
            "emails_10000": cost_per * 10_000,
            "emails_100000": cost_per * 100_000,
        },
        "input_tokens_total": tokens,
        "confidence_histogram": [
            {"lo": i / 10, "hi": (i + 1) / 10, "n": conf_hist[i]} for i in range(10)
        ],
        "uncertain_rate": (uncertain / n) if n else 0.0,
        "errors": errors,
        "rate_limited": limited,
        "retries": retries,
        "gmail_agreement": (agree / labeled) if labeled else 0.0,
        "volume": [{"bucket": p["bucket"], "counts": p["counts"]} for p in series],
        "series": series,
    }
