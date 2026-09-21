"""Classify pipeline, schema, timings, CLI/API. TypeSafeClient is mocked."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from email_classifier.cli.app import app as cli_app
from email_classifier.config import AppConfig
from email_classifier.ingest.db import Database
from email_classifier.jev.client import JevClient, RetryCounter, extract_answers
from email_classifier.jev.questions import QUESTIONS
from email_classifier.models.result import ClassificationResult, format_compact
from email_classifier.pipeline import classify_message
from tests.conftest import make_raw_email
from tests.fakes import FakeResponse, FakeSdk

FIXTURE_EML = Path(__file__).parent / "fixtures" / "eml" / "plain_ham.eml"


def _seed(db: Database, message_id: str = "msg1", raw: bytes | None = None) -> None:
    db.upsert_message(
        message_id,
        "thread1",
        1_700_000_000_000,
        "1",
        raw or FIXTURE_EML.read_bytes(),
        ["INBOX"],
        "alice@example.com",
        "Lunch tomorrow?",
    )


def _classify(app_config: AppConfig, db: Database, sdk: FakeSdk, message_id: str = "msg1"):
    client = JevClient(sdk_client=sdk)
    return classify_message(
        message_id, app_config, jev_client=client, db=db, persist=True
    )


class TestQuestions:
    def test_one_call_six_questions(self) -> None:
        assert set(QUESTIONS) == {
            "category",
            "is_spam",
            "needs_reply",
            "credential_request",
            "brand_impersonation",
            "pressure",
        }


class TestExtractAnswers:
    def test_reads_model_and_usage(self) -> None:
        resp = FakeResponse(model="jev-1.13.0", input_tokens=321)
        answers = extract_answers(resp, RetryCounter(), 12)
        assert answers.model == "jev-1.13.0"
        assert answers.input_tokens == 321


class TestPipeline:
    def test_schema_happy_path(self, app_config: AppConfig, db: Database) -> None:
        _seed(db)
        sdk = FakeSdk(FakeResponse())
        result = _classify(app_config, db, sdk)
        ClassificationResult.model_validate(result.model_dump())
        assert result.category == "spam"
        assert result.spam is True
        assert result.observability.model_version == "jev-1.13.0"
        assert result.observability.input_tokens_estimated is False
        assert result.observability.input_tokens == 400
        assert sdk.calls[0]["model"] == "jev-1.13.0"
        assert set(sdk.calls[0]["questions"]) == set(QUESTIONS)
        assert "body_excerpt" in sdk.calls[0]["state"]

    def test_persists_classification(self, app_config: AppConfig, db: Database) -> None:
        _seed(db)
        _classify(app_config, db, FakeSdk())
        row = db.conn.execute("SELECT COUNT(*) AS n FROM classifications").fetchone()
        assert row["n"] == 1

    def test_uncertain_schema(self, app_config: AppConfig, db: Database) -> None:
        _seed(db)
        sdk = FakeSdk(FakeResponse(category="spam", confidence=0.2, is_spam=0.1))
        result = _classify(app_config, db, sdk)
        ClassificationResult.model_validate(result.model_dump())
        assert result.category == "uncertain"
        assert result.observability.decision_path == "uncertain_floor"

    def test_error_schema(self, app_config: AppConfig, db: Database) -> None:
        _seed(db)
        sdk = FakeSdk(error=RuntimeError("jev down"))
        result = _classify(app_config, db, sdk)
        ClassificationResult.model_validate(result.model_dump())
        assert result.observability.decision_path == "jev_error"
        assert result.category == "uncertain"

    def test_estimated_tokens(self, app_config: AppConfig, db: Database) -> None:
        _seed(db)
        sdk = FakeSdk(FakeResponse(input_tokens=None))
        result = _classify(app_config, db, sdk)
        assert result.observability.input_tokens_estimated is True
        assert result.observability.input_tokens >= 1

    def test_timing_sum(self, app_config: AppConfig, db: Database) -> None:
        _seed(db)
        result = _classify(app_config, db, FakeSdk())
        t = result.classification_time_ms
        summed = t.gmail_fetch + t.parse + t.state_build + t.jev_call + t.decision
        assert abs(t.total - summed) <= 5

    def test_compact_line(self, app_config: AppConfig, db: Database) -> None:
        _seed(db)
        result = _classify(app_config, db, FakeSdk())
        line = format_compact(result)
        assert line.startswith("[SPAM ")
        assert "category=spam" in line
        assert "model=jev-1.13.0" in line
        assert "time=" in line and "jev " in line


class TestRetryCounter:
    def test_counts_429s(self) -> None:
        c = RetryCounter()
        c.record_status(200)
        assert c.retries == 0
        assert c.rate_limited is False
        c.record_status(429)
        c.record_status(429)
        assert c.retries == 2
        assert c.rate_limited is True


class TestCli:
    def test_json_and_compact(
        self, app_config: AppConfig, db: Database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed(db)
        sdk = FakeSdk()
        from email_classifier import pipeline as pipeline_mod

        real = pipeline_mod.classify_message

        def fake(message_id, cfg, **kwargs):
            return real(
                message_id,
                app_config,
                jev_client=JevClient(sdk_client=sdk),
                db=db,
            )

        monkeypatch.setattr("email_classifier.pipeline.classify_message", fake)
        runner = CliRunner()
        json_out = runner.invoke(
            cli_app, ["classify", "msg1", "--json", "--config", "config.yaml"]
        )
        assert json_out.exit_code == 0, json_out.output
        ClassificationResult.model_validate_json(json_out.output)

        compact = runner.invoke(cli_app, ["classify", "msg1", "--config", "config.yaml"])
        assert compact.exit_code == 0, compact.output
        assert "model=jev-1.13.0" in compact.output
        assert "category=" in compact.output


class TestApi:
    def test_post_classify(self, app_config: AppConfig, db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
        _seed(db)
        sdk = FakeSdk()

        def fake(message_id: str, cfg, **kwargs):
            return classify_message(
                message_id, app_config, jev_client=JevClient(sdk_client=sdk), db=db
            )

        import importlib

        api_mod = importlib.import_module("email_classifier.api.app")
        monkeypatch.setattr(api_mod, "classify_message", fake)
        monkeypatch.setattr(api_mod, "load_config", lambda: app_config)
        client = TestClient(api_mod.app)
        resp = client.post("/classify", json={"message_id": "msg1"})
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        ClassificationResult.model_validate(payload)
        assert payload["message_id"] == "msg1"
