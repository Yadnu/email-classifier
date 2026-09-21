"""Precision/recall/F1, calibration, percentiles, and threshold sweep."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class BinaryScores:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int
    tn: int
    support: int  # true positives + false negatives


@dataclass(frozen=True)
class CalibrationBin:
    lo: float
    hi: float
    n: int
    mean_predicted: float
    actual_rate: float


def binary_scores(y_true: Sequence[bool], y_pred: Sequence[bool]) -> BinaryScores:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")
    tp = fp = fn = tn = 0
    for truth, pred in zip(y_true, y_pred):
        if truth and pred:
            tp += 1
        elif pred and not truth:
            fp += 1
        elif truth and not pred:
            fn += 1
        else:
            tn += 1
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    return BinaryScores(
        precision=prec,
        recall=rec,
        f1=f1,
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        support=tp + fn,
    )


def confusion_matrix(
    truths: Sequence[str],
    preds: Sequence[str],
    labels: Sequence[str],
) -> list[list[int]]:
    index = {label: i for i, label in enumerate(labels)}
    size = len(labels)
    matrix = [[0 for _ in range(size)] for _ in range(size)]
    for truth, pred in zip(truths, preds):
        if truth not in index or pred not in index:
            continue
        matrix[index[truth]][index[pred]] += 1
    return matrix


def calibration_table(
    predicted: Sequence[float],
    actual: Sequence[bool],
    bins: int = 10,
) -> list[CalibrationBin]:
    if bins < 1:
        raise ValueError("bins must be >= 1")
    width = 1.0 / bins
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for prob, flag in zip(predicted, actual):
        p = min(max(float(prob), 0.0), 1.0)
        idx = min(int(p / width), bins - 1)
        buckets[idx].append((p, flag))
    out: list[CalibrationBin] = []
    for i, bucket in enumerate(buckets):
        lo = i * width
        hi = 1.0 if i == bins - 1 else (i + 1) * width
        n = len(bucket)
        if n == 0:
            out.append(CalibrationBin(lo=lo, hi=hi, n=0, mean_predicted=0.0, actual_rate=0.0))
            continue
        mean_p = sum(p for p, _ in bucket) / n
        rate = sum(1 for _, flag in bucket if flag) / n
        out.append(
            CalibrationBin(lo=lo, hi=hi, n=n, mean_predicted=mean_p, actual_rate=rate)
        )
    return out


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if p <= 0:
        return ordered[0]
    if p >= 100:
        return ordered[-1]
    rank = (p / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def percentiles(values: Sequence[float], ps: Iterable[float] = (50, 95, 99)) -> dict[float, float]:
    return {p: percentile(values, p) for p in ps}


@dataclass(frozen=True)
class SweepRow:
    threshold: float
    scores: BinaryScores


def threshold_sweep(
    y_true: Sequence[bool],
    probabilities: Sequence[float],
    thresholds: Sequence[float],
) -> list[SweepRow]:
    rows: list[SweepRow] = []
    for threshold in thresholds:
        preds = [prob > threshold for prob in probabilities]
        rows.append(SweepRow(threshold=threshold, scores=binary_scores(y_true, preds)))
    return rows


def best_precision_threshold(rows: Sequence[SweepRow]) -> SweepRow:
    """Highest precision; ties broken by F1, then higher threshold."""
    if not rows:
        raise ValueError("sweep is empty")
    return max(rows, key=lambda row: (row.scores.precision, row.scores.f1, row.threshold))
