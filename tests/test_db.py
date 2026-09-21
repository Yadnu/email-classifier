"""Tests for email_classifier.ingest.db (SQLite schema and helpers).

Uses a temp-file database — no network calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from email_classifier.ingest.db import Database
from tests.conftest import make_raw_email


class TestDatabaseOpen:
    def test_creates_tables(self, db: Database) -> None:
        tables = {
            row[0]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "messages" in tables
        assert "sync_state" in tables
        assert "classifications" in tables

    def test_context_manager(self, tmp_data_dir: Path) -> None:
        db_path = str(tmp_data_dir / "ctx.db")
        with Database(db_path) as d:
            assert d.count_messages() == 0


class TestHistoryId:
    def test_get_history_id_none_on_fresh_db(self, db: Database) -> None:
        assert db.get_history_id() is None

    def test_set_and_get_history_id(self, db: Database) -> None:
        db.set_history_id("99999")
        assert db.get_history_id() == "99999"

    def test_history_id_upsert(self, db: Database) -> None:
        db.set_history_id("100")
        db.set_history_id("200")
        assert db.get_history_id() == "200"


class TestUpsertMessage:
    def _insert(self, db: Database, msg_id: str = "m1", label_ids: list[str] | None = None) -> bool:
        return db.upsert_message(
            message_id=msg_id,
            thread_id="t1",
            internal_date=1_700_000_000_000,
            history_id="10001",
            raw_rfc822=make_raw_email(),
            label_ids=label_ids or ["INBOX"],
            from_header="sender@example.com",
            subject="Test subject",
        )

    def test_insert_returns_true(self, db: Database) -> None:
        assert self._insert(db, "m1") is True

    def test_second_upsert_returns_false(self, db: Database) -> None:
        self._insert(db, "m1")
        assert self._insert(db, "m1") is False

    def test_count_increments_on_insert(self, db: Database) -> None:
        self._insert(db, "m1")
        self._insert(db, "m2")
        assert db.count_messages() == 2

    def test_duplicate_does_not_increment_count(self, db: Database) -> None:
        self._insert(db, "m1")
        self._insert(db, "m1")
        assert db.count_messages() == 1

    def test_message_exists(self, db: Database) -> None:
        assert db.message_exists("m1") is False
        self._insert(db, "m1")
        assert db.message_exists("m1") is True

    def test_label_ids_round_trip(self, db: Database) -> None:
        self._insert(db, "m1", label_ids=["INBOX", "UNREAD", "SPAM"])
        labels = db.get_label_ids("m1")
        assert set(labels) == {"INBOX", "UNREAD", "SPAM"}

    def test_get_message_row(self, db: Database) -> None:
        self._insert(db, "m1")
        row = db.get_message_row("m1")
        assert row is not None
        assert row["message_id"] == "m1"
        assert row["thread_id"] == "t1"


class TestGetThreadSentDates:
    def test_returns_sent_messages_in_thread(self, db: Database) -> None:
        # Insert two messages in the same thread, one SENT and one INBOX.
        db.upsert_message(
            "inbox_msg", "thread1", 1_000_000, "1", make_raw_email(),
            ["INBOX"], "a@example.com", "hello"
        )
        db.upsert_message(
            "sent_msg", "thread1", 2_000_000, "2", make_raw_email(),
            ["SENT"], "me@example.com", "re: hello"
        )
        # The label check uses LIKE '%SENT%' on the JSON, so we need the actual
        # query to run against real DB data.
        pairs = db.get_thread_sent_dates("thread1")
        ids = [p[0] for p in pairs]
        assert "sent_msg" in ids
        assert "inbox_msg" not in ids

    def test_empty_when_no_sent_messages(self, db: Database) -> None:
        db.upsert_message(
            "inbox_msg", "thread2", 1_000_000, "1", make_raw_email(),
            ["INBOX"], "a@example.com", "hi"
        )
        assert db.get_thread_sent_dates("thread2") == []


class TestIterAllMessages:
    def test_yields_all_rows_in_batches(self, db: Database) -> None:
        raw = make_raw_email()
        for i in range(5):
            db.upsert_message(
                f"m{i}", "t1", 1_000_000 + i, "1", raw, ["INBOX"],
                "a@example.com", "subj"
            )
        collected = []
        for batch in db.iter_all_messages(batch_size=2):
            collected.extend(batch)
        assert len(collected) == 5


class TestUnclassified:
    def _msg(self, db: Database, msg_id: str, date: int) -> None:
        db.upsert_message(
            msg_id,
            "t1",
            date,
            "1",
            make_raw_email(),
            ["INBOX"],
            "a@example.com",
            "subj",
        )

    def test_newest_unclassified_skips_seed_and_classified(
        self, db: Database
    ) -> None:
        self._msg(db, "old", 1)
        self._msg(db, "new", 9)
        self._msg(db, "seed-0001", 99)
        db.save_classification("old", "{}")
        assert db.unclassified_message_ids(limit=10) == ["new"]
        assert db.count_unclassified() == 1

