"""Shared pytest fixtures for Stage 1 tests.

All fixtures use synthetic / fake data.  No real email addresses, subjects,
or message bodies are ever used in tests.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from email_classifier.config import AppConfig, GmailConfig, IngestConfig
from email_classifier.ingest.db import Database
from email_classifier.observability import setup_observability


# ─── observability (in-memory spans; must install TracerProvider first) ───────


@pytest.fixture(scope="session", autouse=True)
def otel_exporter():
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    setup_observability(exporter=exporter)
    return exporter


@pytest.fixture(autouse=True)
def _clear_spans(otel_exporter):
    otel_exporter.clear()
    yield otel_exporter


# ─── temp directories ─────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    """A temporary data/ directory that is cleaned up after each test."""
    data = tmp_path / "data"
    data.mkdir()
    return data


# ─── config ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def app_config(tmp_data_dir: Path) -> AppConfig:
    """An AppConfig pointing at the temp directory."""
    cfg = AppConfig()
    cfg.gmail.credentials_path = str(tmp_data_dir / "credentials.json")
    cfg.gmail.token_path = str(tmp_data_dir / "token.json")
    cfg.ingest.db_path = str(tmp_data_dir / "classifier.db")
    cfg.ingest.batch_size = 2   # small for tests
    cfg.ingest.page_size = 10
    cfg.ingest.max_messages = None
    cfg.ingest.promotions_as = "promotional"
    return cfg


# ─── database ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db(tmp_data_dir: Path) -> Database:
    """An open in-memory-style Database backed by a temp file."""
    d = Database(str(tmp_data_dir / "test.db"))
    d.open()
    yield d
    d.close()


# ─── synthetic message factories ──────────────────────────────────────────────

# Fake raw RFC 5322 bytes for a plain-text email.
def make_raw_email(
    subject: str = "Test subject",
    from_addr: str = "sender@example.com",
    body: str = "Hello world",
) -> bytes:
    return (
        f"From: {from_addr}\r\n"
        f"Subject: {subject}\r\n"
        f"Content-Type: text/plain\r\n"
        f"\r\n"
        f"{body}\r\n"
    ).encode()


def make_gmail_message(
    msg_id: str = "msg001",
    thread_id: str = "thread001",
    label_ids: list[str] | None = None,
    internal_date: int = 1_700_000_000_000,
    history_id: str = "10001",
    subject: str = "Test subject",
    from_addr: str = "sender@example.com",
    body: str = "Hello world",
) -> dict[str, Any]:
    """Return an enriched message dict matching the shape from gmail.batch_get_messages."""
    import base64

    raw_bytes = make_raw_email(subject=subject, from_addr=from_addr, body=body)
    return {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": label_ids or ["INBOX"],
        "internalDate": internal_date,
        "historyId": history_id,
        "raw_bytes": raw_bytes,
        "from_header": from_addr,
        "subject": subject,
    }
