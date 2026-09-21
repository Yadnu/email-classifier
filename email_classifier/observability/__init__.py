"""OpenTelemetry tracing, Prometheus metrics, and structlog configuration."""

from email_classifier.observability.logging import log_classification, setup_logging
from email_classifier.observability.metrics import REGISTRY, record_classification
from email_classifier.observability.setup import setup_observability
from email_classifier.observability.tracing import (
    CHILD_SPANS,
    SPAN_CLASSIFY,
    current_trace_id,
    get_tracer,
    set_safe_span_attributes,
    setup_tracing,
)

__all__ = [
    "CHILD_SPANS",
    "REGISTRY",
    "SPAN_CLASSIFY",
    "current_trace_id",
    "get_tracer",
    "log_classification",
    "record_classification",
    "set_safe_span_attributes",
    "setup_logging",
    "setup_observability",
    "setup_tracing",
]
