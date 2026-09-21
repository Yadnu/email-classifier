"""OpenTelemetry tracing: one parent span per classification, five child spans.

Span attributes are restricted to observability fields. Email content is never
attached (no subject, address, body, or raw bytes).
"""
from __future__ import annotations

import os
from typing import Any, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Tracer

SERVICE_NAME = "email-classifier"
SPAN_CLASSIFY = "classify"
CHILD_SPANS = ("gmail_fetch", "parse", "state_build", "jev_call", "decision")

# Only these keys may be written onto spans.
SAFE_SPAN_ATTRS = (
    "request_id",
    "trace_id",
    "model_version",
    "input_tokens",
    "input_tokens_estimated",
    "cost_usd",
    "state_size_chars",
    "body_truncated",
    "retries",
    "rate_limited",
    "decision_path",
    "timestamp",
    "threshold_spam",
    "threshold_phishing",
    "threshold_uncertain_floor",
)

_provider: Optional[TracerProvider] = None


def get_tracer() -> Tracer:
    return trace.get_tracer(SERVICE_NAME)


def current_trace_id() -> Optional[str]:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx is None or not ctx.is_valid:
        return None
    return format(ctx.trace_id, "032x")


def setup_tracing(
    *,
    exporter: Optional[SpanExporter] = None,
    otlp_endpoint: Optional[str] = None,
    force: bool = False,
) -> TracerProvider:
    """Install a TracerProvider. Idempotent unless ``force=True``.

    If ``exporter`` is given (tests), it is used with a SimpleSpanProcessor.
    Otherwise an OTLP exporter is attached when an endpoint is configured
    (``OTEL_EXPORTER_OTLP_ENDPOINT`` or ``otlp_endpoint``).
    """
    global _provider
    if _provider is not None and not force:
        if exporter is not None:
            _provider.add_span_processor(SimpleSpanProcessor(exporter))
        return _provider

    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            from urllib.parse import urlparse

            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            parsed = urlparse(endpoint)
            grpc_target = parsed.netloc or parsed.path or endpoint
            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(endpoint=grpc_target, insecure=True)
                )
            )

    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def set_safe_span_attributes(span: Any, attrs: dict[str, Any]) -> None:
    """Set only allow-listed primitive attributes on ``span``."""
    if span is None:
        return
    for key in SAFE_SPAN_ATTRS:
        if key not in attrs:
            continue
        value = attrs[key]
        if isinstance(value, (str, bool, int, float)) and value is not None:
            span.set_attribute(key, value)
