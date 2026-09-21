"""Evaluate stored classifications against Gmail ground-truth labels."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from email_classifier.config import AppConfig
from email_classifier.eval.baseline import baseline_predicts_spam
from email_classifier.eval.metrics import (
    BinaryScores,
    CalibrationBin,
    SweepRow,
    best_precision_threshold,
    binary_scores,
    calibration_table,
    percentiles,
    threshold_sweep,
)
from email_classifier.ingest.db import Database
from email_classifier.ingest.ground_truth import is_replied_in_thread, label_for_message
from email_classifier.models.result import ClassificationResult

TRUTH_LABELS = ("spam", "ham", "promotional")
PRED_LABELS = ("spam", "phishing", "promotional", "legitimate", "other", "uncertain")
SWEEP_THRESHOLDS = tuple(round(0.50 + 0.05 * i, 2) for i in range(10))


@dataclass
class LabeledExample:
    message_id: str
    truth: str
    replied: bool
    result: ClassificationResult
    raw_rfc822: Optional[bytes]


@dataclass
class EvaluateReport:
    n: int
    truth_counts: dict[str, int]
    spam: BinaryScores
    confusion: list[list[int]]
    truth_labels: tuple[str, ...]
    pred_labels: tuple[str, ...]
    spam_calibration: list[CalibrationBin]
    reply_calibration: list[CalibrationBin]
    sweep: list[SweepRow]
    best_threshold: Optional[SweepRow]
    baseline: Optional[BinaryScores]
    baseline_n: int
    cost_total: float
    cost_per_email: float
    latency_total: dict[float, float]
    latency_jev: dict[float, float]


def _raw_bytes(value: object) -> Optional[bytes]:
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return value
    return None


def load_examples(db: Database, promotions_as: str) -> list[LabeledExample]:
    sent_cache: dict[str, list[tuple[str, int]]] = {}
    examples: list[LabeledExample] = []
    for row in db.latest_classifications():
        labels = json.loads(row["label_ids"])
        truth = label_for_message(labels, promotions_as=promotions_as)
        if truth is None:
            continue
        result = ClassificationResult.model_validate_json(row["result_json"])
        thread_id = row["thread_id"]
        if thread_id not in sent_cache:
            sent_cache[thread_id] = db.get_thread_sent_dates(thread_id)
        replied = is_replied_in_thread(
            row["message_id"],
            row["internal_date"],
            sent_cache[thread_id],
        )
        examples.append(
            LabeledExample(
                message_id=row["message_id"],
                truth=truth,
                replied=replied,
                result=result,
                raw_rfc822=_raw_bytes(row["raw_rfc822"]),
            )
        )
    return examples


def run_evaluate(cfg: AppConfig, db: Optional[Database] = None) -> EvaluateReport:
    owns = db is None
    if db is None:
        db = Database(cfg.ingest.db_path)
        db.open()
    try:
        examples = load_examples(db, cfg.ingest.promotions_as)
        if not examples:
            raise ValueError(
                "No stored classifications to evaluate. "
                "Run `email-classifier classify <id>` first."
            )

        y_true_spam = [ex.truth == "spam" for ex in examples]
        y_pred_spam = [ex.result.spam for ex in examples]
        spam = binary_scores(y_true_spam, y_pred_spam)

        truths = [ex.truth for ex in examples]
        preds = [ex.result.category for ex in examples]
        confusion = [[0 for _ in PRED_LABELS] for _ in TRUTH_LABELS]
        t_index = {label: i for i, label in enumerate(TRUTH_LABELS)}
        p_index = {label: i for i, label in enumerate(PRED_LABELS)}
        for truth, pred in zip(truths, preds):
            if truth in t_index and pred in p_index:
                confusion[t_index[truth]][p_index[pred]] += 1

        spam_cal = calibration_table(
            [ex.result.spam_probability for ex in examples],
            y_true_spam,
        )
        reply_cal = calibration_table(
            [ex.result.reply_probability for ex in examples],
            [ex.replied for ex in examples],
        )
        sweep = threshold_sweep(
            y_true_spam,
            [ex.result.spam_probability for ex in examples],
            SWEEP_THRESHOLDS,
        )
        best = best_precision_threshold(sweep)

        baseline_true: list[bool] = []
        baseline_pred: list[bool] = []
        for ex in examples:
            if not ex.raw_rfc822:
                continue
            try:
                baseline_pred.append(baseline_predicts_spam(ex.raw_rfc822))
            except Exception:
                continue
            baseline_true.append(ex.truth == "spam")
        baseline = (
            binary_scores(baseline_true, baseline_pred) if baseline_true else None
        )

        costs = [ex.result.observability.cost_usd for ex in examples]
        totals = [float(ex.result.classification_time_ms.total) for ex in examples]
        jevs = [float(ex.result.classification_time_ms.jev_call) for ex in examples]
        truth_counts = {label: truths.count(label) for label in TRUTH_LABELS}

        return EvaluateReport(
            n=len(examples),
            truth_counts=truth_counts,
            spam=spam,
            confusion=confusion,
            truth_labels=TRUTH_LABELS,
            pred_labels=PRED_LABELS,
            spam_calibration=spam_cal,
            reply_calibration=reply_cal,
            sweep=sweep,
            best_threshold=best,
            baseline=baseline,
            baseline_n=len(baseline_true),
            cost_total=sum(costs),
            cost_per_email=sum(costs) / len(examples),
            latency_total=percentiles(totals),
            latency_jev=percentiles(jevs),
        )
    finally:
        if owns:
            db.close()


def format_evaluate_report(report: EvaluateReport) -> str:
    s = report.spam
    lines = [
        f"Evaluated {report.n:,}  "
        f"(spam={report.truth_counts.get('spam', 0):,}  "
        f"ham={report.truth_counts.get('ham', 0):,}  "
        f"promotional={report.truth_counts.get('promotional', 0):,})",
        "",
        "Spam verdict vs Gmail SPAM",
        f"  precision={s.precision:.3f}  recall={s.recall:.3f}  "
        f"f1={s.f1:.3f}  support={s.support}",
        f"  TP={s.tp}  FP={s.fp}  FN={s.fn}  TN={s.tn}",
        "",
        "Confusion  (truth \\ pred)",
        "  " + "".join(f"{label:>13}" for label in report.pred_labels),
    ]
    for truth, row in zip(report.truth_labels, report.confusion):
        cells = "".join(f"{n:>13}" for n in row)
        lines.append(f"  {truth:<10}{cells}")

    def _cal_block(title: str, bins: list[CalibrationBin]) -> None:
        lines.append("")
        lines.append(title)
        lines.append(f"  {'bin':<10} {'n':>5} {'mean_pred':>10} {'actual':>8}")
        for b in bins:
            if b.n == 0:
                continue
            lines.append(
                f"  {b.lo:.1f}-{b.hi:.1f}  {b.n:>5}  {b.mean_predicted:>10.3f}  {b.actual_rate:>8.3f}"
            )

    _cal_block("Calibration  (spam_probability)", report.spam_calibration)
    _cal_block("Reply calibration  (reply_probability vs later SENT)", report.reply_calibration)

    lines.append("")
    lines.append("Threshold sweep  (spam if probability > t; optimize precision)")
    lines.append(f"  {'t':>5}  {'P':>6}  {'R':>6}  {'F1':>6}")
    for row in report.sweep:
        sc = row.scores
        mark = "  *" if report.best_threshold and row.threshold == report.best_threshold.threshold else ""
        lines.append(
            f"  {row.threshold:5.2f}  {sc.precision:6.3f}  {sc.recall:6.3f}  {sc.f1:6.3f}{mark}"
        )
    if report.best_threshold:
        b = report.best_threshold
        lines.append(
            f"  best precision: t={b.threshold:.2f}  "
            f"P={b.scores.precision:.3f}  R={b.scores.recall:.3f}"
        )

    lines.append("")
    if report.baseline is None:
        lines.append("Baseline  (SPF/DKIM fail or From!=Reply-To)  n=0")
    else:
        b = report.baseline
        lines.append(
            f"Baseline  (SPF/DKIM fail or From!=Reply-To)  n={report.baseline_n}"
        )
        lines.append(
            f"  precision={b.precision:.3f}  recall={b.recall:.3f}  f1={b.f1:.3f}"
        )

    lines.append("")
    lines.append(
        f"Cost  total=${report.cost_total:.6f}  per email=${report.cost_per_email:.6f}"
    )
    lt, lj = report.latency_total, report.latency_jev
    lines.append(
        f"Latency total p50/p95/p99 = "
        f"{lt[50]:.0f}/{lt[95]:.0f}/{lt[99]:.0f} ms"
    )
    lines.append(
        f"Latency jev   p50/p95/p99 = "
        f"{lj[50]:.0f}/{lj[95]:.0f}/{lj[99]:.0f} ms"
    )
    return "\n".join(lines)
