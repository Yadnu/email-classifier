"""Idempotent observability bootstrap (tracing + JSON logs). Metrics are import-time."""
from __future__ import annotations

from typing import Optional

from opentelemetry.sdk.trace.export import SpanExporter

from email_classifier.observability.logging import setup_logging
from email_classifier.observability.tracing import setup_tracing

_ready = False


def setup_observability(
    *,
    exporter: Optional[SpanExporter] = None,
    otlp_endpoint: Optional[str] = None,
    force: bool = False,
) -> None:
    global _ready
    if _ready and not force:
        return
    setup_logging(force=force)
    setup_tracing(exporter=exporter, otlp_endpoint=otlp_endpoint, force=force)
    _ready = True
