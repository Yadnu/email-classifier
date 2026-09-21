"""Stage 6 label-inbox. Fake Gmail only — never real mail or network."""
from __future__ import annotations

from unittest.mock import MagicMock

from typer.testing import CliRunner

from email_classifier.auth.oauth import modify_token_path
from email_classifier.cli.app import app as cli_app
from email_classifier.config import AppConfig
from email_classifier.ingest.db import Database
from email_classifier.label.gmail_labels import add_labels, ensure_allowed_labels
from email_classifier.label.inbox import format_label_report, run_label_inbox
from email_classifier.label.plan import (
    JEV_NEEDS_REPLY,
    JEV_PHISHING,
    JEV_SPAM,
    planned_labels,
)
from tests.conftest import make_raw_email
from tests.test_eval import _result


class _Exec:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class FakeGmail:
    def __init__(self, existing: list[dict] | None = None) -> None:
        self.existing = list(existing or [])
        self.created: list[dict] = []
        self.modified: list[tuple[str, dict]] = []

    def users(self):
        return self

    def labels(self):
        return self

    def messages(self):
        return self

    def list(self, userId="me"):
        return _Exec({"labels": list(self.existing)})

    def create(self, userId="me", body=None):
        assert body["name"] in {JEV_SPAM, JEV_PHISHING, JEV_NEEDS_REPLY}
        item = {"id": "id-" + body["name"], "name": body["name"]}
        self.existing.append(item)
        self.created.append(body)
        return _Exec(item)

    def modify(self, userId="me", id=None, body=None):
        if body.get("removeLabelIds"):
            raise AssertionError("must not remove labels")
        self.modified.append((id, dict(body)))
        return _Exec({})

    def trash(self, *args, **kwargs):
        raise AssertionError("never trash")

    def delete(self, *args, **kwargs):
        raise AssertionError("never delete")


def _seed(
    db: Database,
    message_id: str,
    result,
    labels: list[str] | None = None,
) -> None:
    db.upsert_message(
        message_id,
        "thread-" + message_id,
        1,
        "1",
        make_raw_email(),
        labels or ["INBOX"],
        "sender@example.com",
        "Test subject",
    )
    db.save_classification(message_id, result.model_dump_json())


class TestPlannedLabels:
    def test_spam(self, app_config: AppConfig) -> None:
        names = planned_labels(
            _result("m", category="spam", spam=True, reply_probability=0.1),
            app_config.thresholds,
        )
        assert names == [JEV_SPAM]

    def test_phishing_not_also_spam(self, app_config: AppConfig) -> None:
        names = planned_labels(
            _result("m", category="phishing", spam=True, reply_probability=0.1),
            app_config.thresholds,
        )
        assert names == [JEV_PHISHING]

    def test_needs_reply(self, app_config: AppConfig) -> None:
        names = planned_labels(
            _result(
                "m",
                category="legitimate",
                spam=False,
                reply_probability=0.80,
            ),
            app_config.thresholds,
        )
        assert names == [JEV_NEEDS_REPLY]

    def test_uncertain_never(self, app_config: AppConfig) -> None:
        names = planned_labels(
            _result(
                "m",
                category="uncertain",
                spam=True,
                reply_probability=0.99,
            ),
            app_config.thresholds,
        )
        assert names == []


class TestModifyTokenPath:
    def test_sibling_file(self) -> None:
        from pathlib import Path

        got = Path(modify_token_path("data/token.json"))
        assert got.name == "token_modify.json"
        assert got.parent == Path("data")


class TestDryRun:
    def test_counts_without_gmail(self, app_config: AppConfig, db: Database) -> None:
        _seed(db, "s1", _result("s1", category="spam", spam=True))
        _seed(
            db,
            "u1",
            _result("u1", category="uncertain", spam=True, reply_probability=0.9),
        )
        _seed(
            db,
            "h1",
            _result("h1", category="legitimate", spam=False, reply_probability=0.1),
        )
        report = run_label_inbox(app_config, dry_run=True, db=db)
        assert report.dry_run is True
        assert len(report.actions) == 1
        assert report.actions[0].labels == [JEV_SPAM]
        assert report.skipped_uncertain == 1
        assert report.skipped_no_action == 1
        text = format_label_report(report)
        assert "dry-run" in text
        assert "Jev-Spam=1" in text
        assert "sender@example.com" not in text
        assert "Test subject" not in text


class TestLiveApply:
    def test_adds_only(self, app_config: AppConfig, db: Database) -> None:
        _seed(db, "s1", _result("s1", category="spam", spam=True))
        _seed(
            db,
            "p1",
            _result("p1", category="phishing", spam=True, reply_probability=0.85),
        )
        gmail = FakeGmail()
        report = run_label_inbox(
            app_config, dry_run=False, db=db, gmail_service=gmail
        )
        assert report.applied == 2
        assert {c["name"] for c in gmail.created} == {
            JEV_SPAM,
            JEV_PHISHING,
            JEV_NEEDS_REPLY,
        }
        modified_ids = {mid for mid, _ in gmail.modified}
        assert modified_ids == {"s1", "p1"}
        for _, body in gmail.modified:
            assert list(body.keys()) == ["addLabelIds"]
            assert body["addLabelIds"]

    def test_reuse_existing_label_ids(self, app_config: AppConfig, db: Database) -> None:
        _seed(db, "s1", _result("s1", category="spam", spam=True))
        gmail = FakeGmail(
            existing=[{"id": "already-spam", "name": JEV_SPAM}]
        )
        run_label_inbox(app_config, dry_run=False, db=db, gmail_service=gmail)
        created_names = {c["name"] for c in gmail.created}
        assert JEV_SPAM not in created_names
        assert gmail.modified[0][1]["addLabelIds"] == ["already-spam"]


class TestGmailGuard:
    def test_add_labels_rejects_removes(self) -> None:
        service = MagicMock()
        # Direct call still only sends addLabelIds.
        add_labels(FakeGmail(), "m1", ["Lid"])
        gmail = FakeGmail()
        add_labels(gmail, "m1", ["Lid"])
        assert gmail.modified[0][1] == {"addLabelIds": ["Lid"]}

    def test_ensure_only_allowed_names(self) -> None:
        gmail = FakeGmail()
        ids = ensure_allowed_labels(gmail)
        assert set(ids) == {JEV_SPAM, JEV_PHISHING, JEV_NEEDS_REPLY}


class TestCli:
    def test_default_is_dry_run(
        self, app_config: AppConfig, db: Database, monkeypatch
    ) -> None:
        _seed(db, "s1", _result("s1", category="spam", spam=True))
        app_config.ingest.db_path = db.db_path.as_posix()
        monkeypatch.setattr(
            "email_classifier.cli.app.load_config",
            lambda path="config.yaml": app_config,
        )
        called = {}

        def fake_run(cfg, dry_run=True, **kwargs):
            called["dry_run"] = dry_run
            return run_label_inbox(cfg, dry_run=True, db=db)

        monkeypatch.setattr("email_classifier.label.inbox.run_label_inbox", fake_run)
        runner = CliRunner()
        result = runner.invoke(cli_app, ["label-inbox", "--config", "config.yaml"])
        assert result.exit_code == 0, result.stdout + result.stderr
        assert called.get("dry_run") is True
        assert "dry-run" in result.stdout

    def test_no_dry_run_flag(self, app_config: AppConfig, monkeypatch) -> None:
        monkeypatch.setattr(
            "email_classifier.cli.app.load_config",
            lambda path="config.yaml": app_config,
        )
        seen = {}

        def fake_run(cfg, dry_run=True, **kwargs):
            seen["dry_run"] = dry_run
            from email_classifier.label.inbox import LabelReport

            return LabelReport(dry_run=dry_run)

        monkeypatch.setattr("email_classifier.label.inbox.run_label_inbox", fake_run)
        runner = CliRunner()
        result = runner.invoke(
            cli_app, ["label-inbox", "--no-dry-run", "--config", "config.yaml"]
        )
        assert result.exit_code == 0, result.stdout + result.stderr
        assert seen["dry_run"] is False
