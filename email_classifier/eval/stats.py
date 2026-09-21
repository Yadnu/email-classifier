"""Period stats and drift watch against the previous window of equal length."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from email_classifier.config import AppConfig
from email_classifier.eval.metrics import percentiles
from email_classifier.ingest.db import Database
from email_classifier.ingest.ground_truth import label_for_message
from email_classifier.models.result import ClassificationResult


@dataclass
class PeriodStats:
    start: Optional[datetime]
    end: Optional[datetime]
    n: int = 0
    category_counts: dict[str, int] = field(default_factory=dict)
    mean_confidence: float = 0.0
    uncertain_rate: float = 0.0
    cost_total: float = 0.0
    cost_per_email: float = 0.0
    agreement: float = 0.0
    labeled_n: int = 0
    latency_total: dict[float, float] = field(default_factory=dict)
    latency_jev: dict[float, float] = field(default_factory=dict)


@dataclass
class DriftAlert:
    metric: str
    previous: float
    current: float
    drop_pct: float


@dataclass
class StatsReport:
    current: PeriodStats
    previous: Optional[PeriodStats]
    alerts: list[DriftAlert]
    drift_alert_pct: float


def parse_date(value: Optional[str], *, end_of_day: bool = False) -> Optional[datetime]:
    if value is None or value == "":
        return None
    dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if end_of_day:
        return dt + timedelta(days=1)
    return dt


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _compute_period(
    rows,
    promotions_as: str,
    start: Optional[datetime],
    end: Optional[datetime],
) -> PeriodStats:
    import json

    stats = PeriodStats(start=start, end=end, n=len(rows))
    if not rows:
        stats.latency_total = {50: 0.0, 95: 0.0, 99: 0.0}
        stats.latency_jev = {50: 0.0, 95: 0.0, 99: 0.0}
        return stats

    confidences: list[float] = []
    totals: list[float] = []
    jevs: list[float] = []
    costs: list[float] = []
    uncertain = 0
    agree = 0
    labeled = 0
    for row in rows:
        result = ClassificationResult.model_validate_json(row["result_json"])
        stats.category_counts[result.category] = (
            stats.category_counts.get(result.category, 0) + 1
        )
        confidences.append(result.category_confidence)
        totals.append(float(result.classification_time_ms.total))
        jevs.append(float(result.classification_time_ms.jev_call))
        costs.append(result.observability.cost_usd)
        if result.category == "uncertain":
            uncertain += 1
        labels = json.loads(row["label_ids"])
        truth = label_for_message(labels, promotions_as=promotions_as)
        if truth is not None:
            labeled += 1
            if result.spam == (truth == "spam"):
                agree += 1

    stats.mean_confidence = sum(confidences) / len(confidences)
    stats.uncertain_rate = uncertain / len(rows)
    stats.cost_total = sum(costs)
    stats.cost_per_email = stats.cost_total / len(rows)
    stats.labeled_n = labeled
    stats.agreement = (agree / labeled) if labeled else 0.0
    stats.latency_total = percentiles(totals)
    stats.latency_jev = percentiles(jevs)
    return stats


def _drop_pct(previous: float, current: float) -> float:
    if previous <= 0:
        return 0.0
    return (previous - current) / previous * 100.0


def run_stats(
    cfg: AppConfig,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: Optional[Database] = None,
) -> StatsReport:
    start = parse_date(from_date)
    end = parse_date(to_date, end_of_day=True)
    owns = db is None
    if db is None:
        db = Database(cfg.ingest.db_path)
        db.open()
    try:
        current_rows = db.classifications_in_range(_iso(start), _iso(end))
        current = _compute_period(current_rows, cfg.ingest.promotions_as, start, end)

        previous: Optional[PeriodStats] = None
        alerts: list[DriftAlert] = []
        if start is not None:
            if end is None:
                end = datetime.now(timezone.utc)
            duration = end - start
            prev_start = start - duration
            prev_end = start
            prev_rows = db.classifications_in_range(_iso(prev_start), _iso(prev_end))
            previous = _compute_period(
                prev_rows, cfg.ingest.promotions_as, prev_start, prev_end
            )
            threshold = cfg.stats.drift_alert_pct
            for name, prev_v, curr_v in (
                ("mean confidence", previous.mean_confidence, current.mean_confidence),
                ("Gmail-agreement", previous.agreement, current.agreement),
            ):
                drop = _drop_pct(prev_v, curr_v)
                if previous.n > 0 and drop > threshold:
                    alerts.append(
                        DriftAlert(
                            metric=name,
                            previous=prev_v,
                            current=curr_v,
                            drop_pct=drop,
                        )
                    )

        return StatsReport(
            current=current,
            previous=previous,
            alerts=alerts,
            drift_alert_pct=cfg.stats.drift_alert_pct,
        )
    finally:
        if owns:
            db.close()


def _fmt_day(dt: Optional[datetime]) -> str:
    if dt is None:
        return "..."
    return dt.date().isoformat()


def format_stats_report(report: StatsReport) -> str:
    cur = report.current
    mix = "  ".join(
        f"{name}={count}"
        for name, count in sorted(cur.category_counts.items())
    ) or "none"
    lt, lj = cur.latency_total, cur.latency_jev
    lines = [
        f"Period {_fmt_day(cur.start)} -> {_fmt_day(cur.end)}  n={cur.n:,}",
        f"  latency total p50/p95/p99 = {lt.get(50, 0):.0f}/{lt.get(95, 0):.0f}/{lt.get(99, 0):.0f} ms",
        f"  latency jev   p50/p95/p99 = {lj.get(50, 0):.0f}/{lj.get(95, 0):.0f}/{lj.get(99, 0):.0f} ms",
        f"  categories: {mix}",
        f"  mean confidence={cur.mean_confidence:.3f}",
        f"  uncertain rate={cur.uncertain_rate:.3f}",
        f"  cost total=${cur.cost_total:.6f}  per email=${cur.cost_per_email:.6f}",
        f"  Gmail SPAM agreement={cur.agreement:.3f}  (n={cur.labeled_n})",
    ]
    if report.previous is not None:
        prev = report.previous
        lines.append(
            f"Previous {_fmt_day(prev.start)} -> {_fmt_day(prev.end)}  n={prev.n:,}"
        )
        lines.append(
            f"  mean confidence={prev.mean_confidence:.3f}  "
            f"agreement={prev.agreement:.3f}"
        )
        if report.alerts:
            for alert in report.alerts:
                lines.append(
                    f"ALERT: {alert.metric} dropped {alert.drop_pct:.1f}% "
                    f"({alert.previous:.3f} -> {alert.current:.3f}; "
                    f"threshold {report.drift_alert_pct:g}%)"
                )
        else:
            lines.append(
                f"  drift: no drop above {report.drift_alert_pct:g}% vs previous period"
            )
    elif cur.start is None:
        lines.append("  drift: pass --from YYYY-MM-DD to compare a previous window")
    return "\n".join(lines)
