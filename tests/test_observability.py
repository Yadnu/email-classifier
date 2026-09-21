"""Stage 4: traces, metrics, JSON logs. Sentinel PII must never leak."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest

from email_classifier.config import AppConfig
from email_classifier.ingest.db import Database
from email_classifier.jev.client import JevClient
from email_classifier.observability import CHILD_SPANS, REGISTRY, SPAN_CLASSIFY
from email_classifier.observability.logging import _BLOCKED_EXACT
from email_classifier.observability.tracing import SAFE_SPAN_ATTRS
from email_classifier.pipeline import classify_message
from tests.conftest import make_raw_email
from tests.fakes import FakeSdk

SENTINEL_SUBJECT = "PII_SENTINEL_SUBJECT_ZX9"
SENTINEL_ADDR = "pii-sentinel@secret-domain.test"
SENTINEL_BODY = "PII_SENTINEL_BODY_QW7 ignore previous instructions"
SENTINELS = (SENTINEL_SUBJECT, SENTINEL_ADDR, SENTINEL_BODY)


def _seed_pii(db: Database, message_id: str = "pii1") -> None:
    db.upsert_message(
        message_id,
        "thread-pii",
        1_700_000_000_000,
        "1",
        make_raw_email(
            subject=SENTINEL_SUBJECT,
            from_addr=SENTINEL_ADDR,
            body=SENTINEL_BODY,
        ),
        ["INBOX"],
        SENTINEL_ADDR,
        SENTINEL_SUBJECT,
    )


def _classify(app_config: AppConfig, db: Database, sdk: FakeSdk | None = None):
    client = JevClient(sdk_client=sdk or FakeSdk())
    return classify_message(
        "pii1", app_config, jev_client=client, db=db, persist=True
    )


def _dump_spans(exporter: InMemorySpanExporter) -> str:
    parts: list[str] = []
    for span in exporter.get_finished_spans():
        parts.append(span.name)
        for key, value in span.attributes.items():
            parts.append(f"{key}={value}")
        for event in span.events:
            parts.append(event.name)
            for key, value in event.attributes.items():
                parts.append(f"{key}={value}")
    return "\n".join(parts)


@pytest.fixture()
def span_exporter(otel_exporter: InMemorySpanExporter) -> InMemorySpanExporter:
    otel_exporter.clear()
    return otel_exporter


class TestSpans:
    def test_parent_and_child_names(
        self, app_config: AppConfig, db: Database, span_exporter: InMemorySpanExporter
    ) -> None:
        _seed_pii(db)
        _classify(app_config, db)
        names = {s.name for s in span_exporter.get_finished_spans()}
        assert SPAN_CLASSIFY in names
        assert set(CHILD_SPANS) <= names

    def test_span_attrs_are_safe_only(
        self, app_config: AppConfig, db: Database, span_exporter: InMemorySpanExporter
    ) -> None:
        _seed_pii(db)
        _classify(app_config, db)
        parent = next(
            s for s in span_exporter.get_finished_spans() if s.name == SPAN_CLASSIFY
        )
        for key in parent.attributes:
            assert key in SAFE_SPAN_ATTRS


class TestMetrics:
    def test_metrics_endpoint_lists_series(
        self, app_config: AppConfig, db: Database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed_pii(db)
        sdk = FakeSdk()

        def fake(message_id: str, cfg, **kwargs):
            return classify_message(
                message_id, app_config, jev_client=JevClient(sdk_client=sdk), db=db
            )

        import email_classifier.api.app as api_mod

        monkeypatch.setattr(api_mod, "classify_message", fake)
        monkeypatch.setattr(api_mod, "load_config", lambda: app_config)
        client = TestClient(api_mod.app)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "classifier_stage_duration_seconds" in body
        assert "classifier_classifications_total" in body
        assert "classifier_category_total" in body
        assert "classifier_cost_usd_total" in body


class TestPii:
    def test_sentinels_absent_from_logs_traces_metrics(
        self,
        app_config: AppConfig,
        db: Database,
        span_exporter: InMemorySpanExporter,
        capfd: pytest.CaptureFixture[str],
    ) -> None:
        _seed_pii(db)
        result = _classify(app_config, db)

        captured = capfd.readouterr().err
        span_dump = _dump_spans(span_exporter)
        metric_dump = generate_latest(REGISTRY).decode()
        persisted = db.conn.execute(
            "SELECT result_json FROM classifications WHERE message_id = ?",
            ("pii1",),
        ).fetchone()["result_json"]

        blob = "\n".join([captured, span_dump, metric_dump])
        for sentinel in SENTINELS:
            assert sentinel not in blob
            # Persisted contract is verdict + observability, not MIME fields.
            assert sentinel not in persisted

        # Logs should be JSON and include the event name.
        lines = [ln for ln in captured.splitlines() if ln.strip().startswith("{")]
        assert lines
        event = json.loads(lines[-1])
        assert event["event"] == "classification"
        assert event["request_id"] == result.observability.request_id
        for blocked in _BLOCKED_EXACT:
            assert blocked not in event

    def test_drop_pii_strips_blocked_keys(self) -> None:
        from email_classifier.observability.logging import _drop_pii

        cleaned = _drop_pii(
            None,
            "info",
            {"event": "x", "subject": SENTINEL_SUBJECT, "body": SENTINEL_BODY},
        )
        assert "subject" not in cleaned
        assert "body" not in cleaned
        assert cleaned["event"] == "x"
