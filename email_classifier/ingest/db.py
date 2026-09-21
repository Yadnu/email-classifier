"""SQLite schema and low-level database helpers.

Schema
------
messages
    message_id      TEXT PRIMARY KEY      -- Gmail message ID
    thread_id       TEXT NOT NULL         -- Gmail thread ID
    internal_date   INTEGER               -- Unix ms from Gmail
    history_id      TEXT                  -- Gmail historyId at ingest time
    raw_rfc822      BLOB                  -- Full RFC 5322 message (base64url decoded)
    label_ids       TEXT                  -- JSON array of Gmail label IDs
    from_header     TEXT                  -- Raw From: header (stored, never logged)
    subject         TEXT                  -- Raw Subject: header (stored, never logged)
    ingested_at     TEXT                  -- ISO 8601 UTC

sync_state
    key             TEXT PRIMARY KEY      -- always 'main'
    history_id      TEXT                  -- last seen historyId from users.getProfile
    updated_at      TEXT                  -- ISO 8601 UTC of last successful sync

classifications
    id              INTEGER PRIMARY KEY AUTOINCREMENT
    message_id      TEXT NOT NULL REFERENCES messages(message_id)
    classified_at   TEXT NOT NULL         -- ISO 8601 UTC
    result_json     TEXT NOT NULL         -- full ClassificationResult JSON (Stage 3)
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    message_id    TEXT PRIMARY KEY,
    thread_id     TEXT NOT NULL,
    internal_date INTEGER,
    history_id    TEXT,
    raw_rfc822    BLOB,
    label_ids     TEXT,
    from_header   TEXT,
    subject       TEXT,
    ingested_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_thread
    ON messages (thread_id);

CREATE INDEX IF NOT EXISTS idx_messages_internal_date
    ON messages (internal_date);

CREATE TABLE IF NOT EXISTS sync_state (
    key        TEXT PRIMARY KEY,
    history_id TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classifications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id    TEXT NOT NULL REFERENCES messages (message_id),
    classified_at TEXT NOT NULL,
    result_json   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_classifications_message
    ON classifications (message_id);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thin wrapper around a SQLite connection with helpers used by ingest."""

    def __init__(self, db_path: str = "data/classifier.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> "Database":
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL mode for better concurrent reads.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        return self

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Database":
        return self.open()

    def __exit__(self, *_: Any) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not open. Use 'with Database(...) as db:'.")
        return self._conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ── sync_state ────────────────────────────────────────────────────────────

    def get_history_id(self) -> Optional[str]:
        """Return the last saved historyId, or None if this is a fresh database."""
        row = self.conn.execute(
            "SELECT history_id FROM sync_state WHERE key = 'main'"
        ).fetchone()
        return row["history_id"] if row else None

    def set_history_id(self, history_id: str) -> None:
        """Upsert the current historyId after a successful sync."""
        with self.transaction() as c:
            c.execute(
                """
                INSERT INTO sync_state (key, history_id, updated_at)
                VALUES ('main', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    history_id = excluded.history_id,
                    updated_at = excluded.updated_at
                """,
                (history_id, _now_iso()),
            )

    # ── messages ──────────────────────────────────────────────────────────────

    def upsert_message(
        self,
        message_id: str,
        thread_id: str,
        internal_date: Optional[int],
        history_id: Optional[str],
        raw_rfc822: Optional[bytes],
        label_ids: list[str],
        from_header: Optional[str],
        subject: Optional[str],
    ) -> bool:
        """Insert or update a message row.

        Returns True if a new row was inserted, False if updated.
        """
        now = _now_iso()
        label_json = json.dumps(label_ids)
        existing = self.conn.execute(
            "SELECT message_id FROM messages WHERE message_id = ?", (message_id,)
        ).fetchone()

        with self.transaction() as c:
            if existing is None:
                c.execute(
                    """
                    INSERT INTO messages
                        (message_id, thread_id, internal_date, history_id,
                         raw_rfc822, label_ids, from_header, subject, ingested_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id,
                        thread_id,
                        internal_date,
                        history_id,
                        raw_rfc822,
                        label_json,
                        from_header,
                        subject,
                        now,
                    ),
                )
                return True
            else:
                # Update label_ids and history_id (raw body stays unchanged).
                c.execute(
                    """
                    UPDATE messages SET
                        label_ids  = ?,
                        history_id = ?
                    WHERE message_id = ?
                    """,
                    (label_json, history_id, message_id),
                )
                return False

    def message_exists(self, message_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        return row is not None

    def get_label_ids(self, message_id: str) -> list[str]:
        row = self.conn.execute(
            "SELECT label_ids FROM messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        if row is None:
            return []
        return json.loads(row["label_ids"])

    def count_messages(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    def get_thread_sent_dates(self, thread_id: str) -> list[tuple[str, int]]:
        """Return (message_id, internal_date) pairs for SENT messages in a thread.

        Used by ground-truth reply detection.
        """
        rows = self.conn.execute(
            """
            SELECT message_id, internal_date
            FROM messages
            WHERE thread_id = ?
              AND json_extract(label_ids, '$') LIKE '%SENT%'
            ORDER BY internal_date ASC
            """,
            (thread_id,),
        ).fetchall()
        return [(r["message_id"], r["internal_date"]) for r in rows]

    def get_message_row(self, message_id: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM messages WHERE message_id = ?", (message_id,)
        ).fetchone()

    def save_classification(self, message_id: str, result_json: str) -> None:
        """Persist a ClassificationResult for historical analysis."""
        with self.transaction() as c:
            c.execute(
                """
                INSERT INTO classifications (message_id, classified_at, result_json)
                VALUES (?, ?, ?)
                """,
                (message_id, _now_iso(), result_json),
            )

    def iter_all_messages(
        self,
        batch_size: int = 200,
    ) -> Generator[list[sqlite3.Row], None, None]:
        """Yield batches of all message rows for bulk processing."""
        offset = 0
        while True:
            rows = self.conn.execute(
                "SELECT * FROM messages ORDER BY internal_date ASC LIMIT ? OFFSET ?",
                (batch_size, offset),
            ).fetchall()
            if not rows:
                break
            yield rows
            offset += len(rows)
