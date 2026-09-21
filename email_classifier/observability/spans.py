"""Build a UI-friendly span tree from classification timings."""
from __future__ import annotations

from typing import Any

from email_classifier.models.result import ClassificationResult, ClassificationTimeMs

STAGE_ORDER = ("gmail_fetch", "parse", "state_build", "jev_call", "decision")


def span_tree_from_result(result: ClassificationResult) -> dict[str, Any]:
    t = result.classification_time_ms
    return span_tree_from_timings(
        t,
        retries=result.observability.retries,
        rate_limited=result.observability.rate_limited,
        attributes={
            "request_id": result.observability.request_id,
            "trace_id": result.observability.trace_id,
            "decision_path": result.observability.decision_path,
        },
    )


def span_tree_from_timings(
    t: ClassificationTimeMs,
    *,
    retries: int = 0,
    rate_limited: bool = False,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total = max(t.total, 0)
    offset = 0
    children: list[dict[str, Any]] = []
    for name in STAGE_ORDER:
        duration = int(getattr(t, name))
        pct = (duration / total * 100.0) if total else 0.0
        child: dict[str, Any] = {
            "name": name,
            "offset_ms": offset,
            "duration_ms": duration,
            "pct_of_total": round(pct, 2),
            "retries": retries if name == "jev_call" else 0,
            "rate_limited": bool(rate_limited) if name == "jev_call" else False,
            "attributes": {},
        }
        children.append(child)
        offset += duration
    return {
        "name": "classify",
        "duration_ms": total,
        "children": children,
        "attributes": dict(attributes or {}),
    }
