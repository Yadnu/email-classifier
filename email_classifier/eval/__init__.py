"""Evaluation pipeline: precision/recall/F1, calibration, threshold sweep."""

from email_classifier.eval.evaluate import EvaluateReport, format_evaluate_report, run_evaluate
from email_classifier.eval.stats import StatsReport, format_stats_report, run_stats

__all__ = [
    "EvaluateReport",
    "StatsReport",
    "format_evaluate_report",
    "format_stats_report",
    "run_evaluate",
    "run_stats",
]
