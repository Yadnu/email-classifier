"""Stage 5 evaluate/stats. Synthetic labels and stored results only."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from email_classifier.cli.app import app as cli_app
from email_classifier.config import AppConfig
from email_classifier.eval.baseline import baseline_predicts_spam
from email_classifier.eval.evaluate import format_evaluate_report, run_evaluate
from email_classifier.eval.metrics import (
    best_precision_threshold,
    binary_scores,
    calibration_table,
    percentile,
    threshold_sweep,
)
from email_classifier.eval.stats import format_stats_report, run_stats
from email_classifier.ingest.db import Database
from email_classifier.models.result import (
    ClassificationResult,
    ClassificationTimeMs,
    Observability,
    Signals,
    ThresholdsApplied,
)
from tests.conftest import make_raw_email

FIXTURES = Path(__file__).parent / "fixtures" / "eml"


def _result(
    message_id: str,
    *,
    category: str = "spam",
    confidence: float = 0.9,
    spam: bool = True,
    spam_probability: float = 0.9,
    reply_probability: float = 0.1,
    cost_usd: float = 0.0001,
    total_ms: int = 200,
    jev_ms: int = 150,
) -> ClassificationResult:
    return ClassificationResult(
        message_id=message_id,
        category=category,  # type: ignore[arg-type]
        category_confidence=confidence,
        category_probabilities={
            "spam": 0.9 if category == "spam" else 0.05,
            "phishing": 0.05,
            "promotional": 0.9 if category == "promotional" else 0.02,
            "legitimate": 0.9 if category == "legitimate" else 0.02,
            "other": 0.01,
        },
        spam=spam,
        spam_probability=spam_probability,
        reply_probability=reply_probability,
        signals=Signals(
            credential_request=0.1,
            brand_impersonation=0.1,
            pressure_score=0.2,
        ),
        classification_time_ms=ClassificationTimeMs(
            total=total_ms,
            gmail_fetch=10,
            parse=10,
            state_build=10,
            jev_call=jev_ms,
            decision=10,
        ),
        observability=Observability(
            request_id="req-" + message_id,
            trace_id="t" * 32,
            model_version="jev-1.13.0",
            input_tokens=100,
            input_tokens_estimated=False,
            cost_usd=cost_usd,
            state_size_chars=200,
            body_truncated=False,
            retries=0,
            rate_limited=False,
            thresholds_applied=ThresholdsApplied(
                spam=0.75, phishing=0.85, uncertain_floor=0.5
            ),
            decision_path="test",
            timestamp="2026-09-01T00:00:00+00:00",
        ),
    )


def _seed_message(
    db: Database,
    message_id: str,
    labels: list[str],
    raw: bytes | None = None,
    thread_id: str | None = None,
    internal_date: int = 1_700_000_000_000,
    classified_at: str | None = None,
    result: ClassificationResult | None = None,
) -> None:
    db.upsert_message(
        message_id,
        thread_id or f"thread-{message_id}",
        internal_date,
        "1",
        raw or make_raw_email(),
        labels,
        "sender@example.com",
        "Test subject",
    )
    if result is None:
        result = _result(message_id, spam=("SPAM" in labels), spam_probability=0.9 if "SPAM" in labels else 0.1)
        result = result.model_copy(update={"spam": "SPAM" in labels})
    db.save_classification(
        message_id,
        result.model_dump_json(),
        classified_at=classified_at,
    )


class TestMetrics:
    def test_perfect_scores(self) -> None:
        s = binary_scores([True, True, False], [True, True, False])
        assert s.precision == 1.0
        assert s.recall == 1.0
        assert s.f1 == 1.0
        assert s.tp == 2 and s.tn == 1

    def test_zero_division(self) -> None:
        s = binary_scores([False, False], [False, False])
        assert s.precision == 0.0
        assert s.recall == 0.0
        assert s.f1 == 0.0

    def test_percentile(self) -> None:
        assert percentile([1, 2, 3, 4, 5], 50) == 3
        assert percentile([], 50) == 0.0

    def test_calibration_bins(self) -> None:
        table = calibration_table([0.05, 0.15, 0.95], [False, False, True], bins=10)
        assert table[0].n == 1
        assert table[0].actual_rate == 0.0
        assert table[9].n == 1
        assert table[9].actual_rate == 1.0

    def test_sweep_picks_highest_precision(self) -> None:
        y_true = [True, True, False, False]
        probs = [0.9, 0.4, 0.6, 0.1]
        rows = threshold_sweep(y_true, probs, [0.3, 0.5, 0.8])
        best = best_precision_threshold(rows)
        assert best.threshold == 0.8
        assert best.scores.precision == 1.0


class TestBaseline:
    def test_auth_fail_is_spam(self) -> None:
        raw = (FIXTURES / "auth_fail_received_spf.eml").read_bytes()
        assert baseline_predicts_spam(raw) is True

    def test_pass_headers_not_spam(self) -> None:
        raw = (FIXTURES / "auth_headers.eml").read_bytes()
        assert baseline_predicts_spam(raw) is False

    def test_mismatch_is_spam(self) -> None:
        raw = (FIXTURES / "from_reply_to_mismatch.eml").read_bytes()
        assert baseline_predicts_spam(raw) is True


class TestEvaluate:
    def test_report_against_gmail_labels(self, app_config: AppConfig, db: Database) -> None:
        _seed_message(
            db,
            "s1",
            ["SPAM"],
            result=_result("s1", spam=True, spam_probability=0.95, category="spam"),
        )
        _seed_message(
            db,
            "s2",
            ["SPAM"],
            result=_result("s2", spam=False, spam_probability=0.2, category="legitimate"),
        )
        _seed_message(
            db,
            "h1",
            ["INBOX"],
            result=_result("h1", spam=False, spam_probability=0.1, category="legitimate"),
        )
        _seed_message(
            db,
            "p1",
            ["CATEGORY_PROMOTIONS"],
            result=_result("p1", spam=False, spam_probability=0.2, category="promotional"),
        )
        report = run_evaluate(app_config, db=db)
        assert report.n == 4
        assert report.truth_counts["spam"] == 2
        assert report.truth_counts["ham"] == 1
        assert report.truth_counts["promotional"] == 1
        assert report.spam.tp == 1
        assert report.spam.fn == 1
        assert report.spam.tn == 2
        assert report.best_threshold is not None
        text = format_evaluate_report(report)
        assert "precision=" in text
        assert "Threshold sweep" in text
        assert "Baseline" in text
        assert "sender@example.com" not in text
        assert "Test subject" not in text

    def test_uses_latest_classification(self, app_config: AppConfig, db: Database) -> None:
        _seed_message(
            db,
            "s1",
            ["SPAM"],
            classified_at="2026-09-01T00:00:00+00:00",
            result=_result("s1", spam=False, spam_probability=0.1),
        )
        db.save_classification(
            "s1",
            _result("s1", spam=True, spam_probability=0.99).model_dump_json(),
            classified_at="2026-09-02T00:00:00+00:00",
        )
        report = run_evaluate(app_config, db=db)
        assert report.spam.tp == 1
        assert report.spam.fn == 0

    def test_reply_calibration(self, app_config: AppConfig, db: Database) -> None:
        _seed_message(
            db,
            "orig",
            ["INBOX"],
            thread_id="t-reply",
            internal_date=1_000,
            result=_result("orig", spam=False, reply_probability=0.9, category="legitimate"),
        )
        db.upsert_message(
            "sent1",
            "t-reply",
            2_000,
            "1",
            make_raw_email(),
            ["SENT"],
            "me@example.com",
            "Re: Test",
        )
        report = run_evaluate(app_config, db=db)
        high = [b for b in report.reply_calibration if b.n and b.lo >= 0.8]
        assert high
        assert high[0].actual_rate == 1.0

    def test_empty_exits(self, app_config: AppConfig, db: Database) -> None:
        try:
            run_evaluate(app_config, db=db)
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "classify" in str(exc)


class TestStats:
    def test_date_window_and_drift(self, app_config: AppConfig, db: Database) -> None:
        app_config.stats.drift_alert_pct = 10
        _seed_message(
            db,
            "old1",
            ["SPAM"],
            classified_at="2026-08-10T12:00:00+00:00",
            result=_result(
                "old1",
                spam=True,
                confidence=0.95,
                category="spam",
                cost_usd=0.001,
                total_ms=100,
            ),
        )
        _seed_message(
            db,
            "new1",
            ["SPAM"],
            classified_at="2026-09-10T12:00:00+00:00",
            result=_result(
                "new1",
                spam=False,
                confidence=0.40,
                category="uncertain",
                cost_usd=0.002,
                total_ms=400,
            ),
        )
        report = run_stats(app_config, from_date="2026-09-01", to_date="2026-09-30", db=db)
        assert report.current.n == 1
        assert report.previous is not None
        assert report.previous.n == 1
        assert report.current.uncertain_rate == 1.0
        assert report.alerts
        names = {a.metric for a in report.alerts}
        assert "mean confidence" in names
        text = format_stats_report(report)
        assert "ALERT" in text
        assert "old1" not in text

    def test_no_from_skips_drift(self, app_config: AppConfig, db: Database) -> None:
        _seed_message(
            db,
            "m1",
            ["INBOX"],
            classified_at="2026-09-10T12:00:00+00:00",
            result=_result("m1", spam=False, category="legitimate"),
        )
        report = run_stats(app_config, db=db)
        assert report.current.n == 1
        assert report.previous is None
        assert not report.alerts


class TestCli:
    def test_evaluate_and_stats(
        self, app_config: AppConfig, db: Database, monkeypatch
    ) -> None:
        _seed_message(
            db,
            "s1",
            ["SPAM"],
            classified_at="2026-09-10T12:00:00+00:00",
            result=_result("s1", spam=True, category="spam"),
        )
        app_config.ingest.db_path = db.db_path.as_posix()
        monkeypatch.setattr(
            "email_classifier.cli.app.load_config", lambda path="config.yaml": app_config
        )
        runner = CliRunner()
        ev = runner.invoke(cli_app, ["evaluate", "--config", "config.yaml"])
        assert ev.exit_code == 0, ev.stdout + ev.stderr
        assert "precision=" in ev.stdout

        st = runner.invoke(
            cli_app,
            ["stats", "--from", "2026-09-01", "--to", "2026-09-30", "--config", "config.yaml"],
        )
        assert st.exit_code == 0, st.stdout + st.stderr
        assert "agreement=" in st.stdout

    def test_bad_date(self, app_config: AppConfig, monkeypatch) -> None:
        monkeypatch.setattr(
            "email_classifier.cli.app.load_config", lambda path="config.yaml": app_config
        )
        runner = CliRunner()
        bad = runner.invoke(cli_app, ["stats", "--from", "09-01-2026"])
        assert bad.exit_code == 1
        assert "YYYY-MM-DD" in bad.stderr
