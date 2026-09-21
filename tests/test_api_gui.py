"""GUI inspect API tests. Fake SQLite only."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from email_classifier.api.live import publish_classification, subscribe, unsubscribe
from email_classifier.config import AppConfig
from email_classifier.ingest.db import Database
from email_classifier.jev.snapshot import snapshot_questions
from tests.conftest import make_raw_email
from tests.test_eval import _result


def _client(app_config: AppConfig, monkeypatch) -> TestClient:
    import email_classifier.api.app as api_mod
    import email_classifier.api.gui as gui_mod

    monkeypatch.setattr(api_mod, "load_config", lambda: app_config)
    monkeypatch.setattr(gui_mod, "load_config", lambda: app_config)
    return TestClient(api_mod.app)


def _seed(db: Database, message_id: str, result, labels=None, subject="Hello") -> None:
    db.upsert_message(
        message_id,
        "th",
        1,
        "1",
        make_raw_email(subject=subject),
        labels or ["INBOX"],
        "alice@shop.example.test",
        subject,
    )
    db.save_classification(
        message_id,
        result.model_dump_json(),
        state_json=json.dumps(
            {
                "sender_display_name": "Alice",
                "sender_address": "alice@shop.example.test",
                "sender_domain": "shop.example.test",
                "reply_to_domain": "shop.example.test",
                "subject": subject,
                "spf_result": "pass",
                "dkim_result": "pass",
                "dmarc_result": "pass",
                "link_domains": [],
                "has_attachments": False,
                "body_excerpt": "Hi",
            }
        ),
        questions_json=json.dumps(snapshot_questions()),
        spans_json="{}",
        answers_json="{}",
    )


class TestGuiApi:
    def test_list_and_detail(self, app_config: AppConfig, db: Database, monkeypatch) -> None:
        app_config.ingest.db_path = db.db_path.as_posix()
        _seed(db, "m1", _result("m1", category="spam", spam=True), labels=["SPAM"])
        client = _client(app_config, monkeypatch)
        listing = client.get("/api/messages")
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert items[0]["message_id"] == "m1"
        assert items[0]["sender_domain"] == "shop.example.test"
        assert items[0]["category"] == "spam"

        detail = client.get("/api/messages/m1")
        assert detail.status_code == 200
        body = detail.json()
        assert body["result"]["message_id"] == "m1"
        assert "is_spam" in body["explanation"].lower() or "spam" in body["explanation"].lower()
        assert body["state"]["sender_domain"] == "shop.example.test"
        types = {q["name"]: q["type"] for q in body["questions"]}
        assert types["category"] == "Choice"
        assert types["is_spam"] == "Noul"
        assert types["pressure"] == "Score"
        assert body["decision_trail"]

    def test_stats_and_calibration(self, app_config: AppConfig, db: Database, monkeypatch) -> None:
        app_config.ingest.db_path = db.db_path.as_posix()
        _seed(db, "m1", _result("m1", category="spam", spam=True), labels=["SPAM"])
        _seed(
            db,
            "m2",
            _result("m2", category="legitimate", spam=False, confidence=0.8),
            labels=["INBOX"],
        )
        client = _client(app_config, monkeypatch)
        stats = client.get("/api/stats").json()
        assert stats["n"] == 2
        assert stats["counts_by_category"]["spam"] == 1
        cal = client.get("/api/calibration").json()
        assert "spam" in cal and "reply" in cal

    def test_health(self, app_config: AppConfig, db: Database, monkeypatch) -> None:
        app_config.ingest.db_path = db.db_path.as_posix()
        client = _client(app_config, monkeypatch)
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["messages"] >= 0

    def test_live_sse(self) -> None:
        q = subscribe()
        try:
            publish_classification({"message_id": "x", "category": "spam"})
            line = next(iter([q.get(timeout=1)]))
            assert "spam" in line
        finally:
            unsubscribe(q)

    def test_replay_mocked(self, app_config: AppConfig, db: Database, monkeypatch) -> None:
        app_config.ingest.db_path = db.db_path.as_posix()
        _seed(db, "m1", _result("m1", category="spam", spam=True))
        from tests.fakes import FakeSdk
        from email_classifier.jev.client import JevClient

        def fake_client(**kwargs):
            return JevClient(sdk_client=FakeSdk())

        monkeypatch.setattr("email_classifier.api.gui.JevClient", fake_client)
        client = _client(app_config, monkeypatch)
        resp = client.post("/api/replay/m1")
        assert resp.status_code == 200
        payload = resp.json()
        assert "previous" in payload and "replayed" in payload
        assert "diff" in payload


class TestExplain:
    def test_is_spam_sentence(self, app_config: AppConfig) -> None:
        from email_classifier.decide.explain import explain_verdict

        result = _result("m", category="spam", spam=True, spam_probability=0.94)
        result.observability.decision_path = "is_spam_noul"
        text = explain_verdict(result, app_config.thresholds)
        assert "0.94" in text
        assert "0.75" in text
