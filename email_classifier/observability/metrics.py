"""Prometheus metrics for classification latency, mix, errors, tokens, and cost."""
from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram

LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
PROB_BUCKETS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)

# Dedicated registry so tests and /metrics share the same series.
REGISTRY = CollectorRegistry()

stage_duration_seconds = Histogram(
    "classifier_stage_duration_seconds",
    "Classification stage latency in seconds (50ms–5s buckets).",
    ["stage"],
    buckets=LATENCY_BUCKETS,
    registry=REGISTRY,
)

classifications_total = Counter(
    "classifier_classifications_total",
    "Classifications completed.",
    registry=REGISTRY,
)

category_total = Counter(
    "classifier_category_total",
    "Classifications by category.",
    ["category"],
    registry=REGISTRY,
)

spam_total = Counter(
    "classifier_spam_total",
    "Classifications whose spam verdict is true.",
    registry=REGISTRY,
)

uncertain_total = Counter(
    "classifier_uncertain_total",
    "Classifications with category=uncertain.",
    registry=REGISTRY,
)

errors_total = Counter(
    "classifier_errors_total",
    "Classifications that hit a Jev or pipeline error path.",
    registry=REGISTRY,
)

rate_limited_total = Counter(
    "classifier_rate_limited_total",
    "Classifications that observed at least one HTTP 429.",
    registry=REGISTRY,
)

retries_total = Counter(
    "classifier_retries_total",
    "Jev HTTP retries (typically 429).",
    registry=REGISTRY,
)

input_tokens_total = Counter(
    "classifier_input_tokens_total",
    "Input tokens consumed (or estimated) by Jev.",
    registry=REGISTRY,
)

cost_usd_total = Counter(
    "classifier_cost_usd_total",
    "Estimated Jev cost in USD (input tokens only).",
    registry=REGISTRY,
)

confidence = Histogram(
    "classifier_confidence",
    "Category confidence of each classification.",
    buckets=PROB_BUCKETS,
    registry=REGISTRY,
)

spam_probability = Histogram(
    "classifier_spam_probability",
    "is_spam probability of each classification.",
    buckets=PROB_BUCKETS,
    registry=REGISTRY,
)


def record_classification(result) -> None:
    """Record Prometheus series from a ClassificationResult. No email content."""
    t = result.classification_time_ms
    for stage, ms in (
        ("total", t.total),
        ("gmail_fetch", t.gmail_fetch),
        ("parse", t.parse),
        ("state_build", t.state_build),
        ("jev_call", t.jev_call),
        ("decision", t.decision),
    ):
        stage_duration_seconds.labels(stage=stage).observe(ms / 1000.0)

    classifications_total.inc()
    category_total.labels(category=result.category).inc()
    if result.spam:
        spam_total.inc()
    if result.category == "uncertain":
        uncertain_total.inc()

    obs = result.observability
    if obs.decision_path == "jev_error":
        errors_total.inc()
    if obs.rate_limited:
        rate_limited_total.inc()
    if obs.retries:
        retries_total.inc(obs.retries)
    input_tokens_total.inc(obs.input_tokens)
    cost_usd_total.inc(obs.cost_usd)
    confidence.observe(result.category_confidence)
    spam_probability.observe(result.spam_probability)
