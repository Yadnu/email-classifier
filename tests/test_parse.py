"""Tests for MIME parsing and HTML stripping. Fake .eml fixtures only."""
from __future__ import annotations

from pathlib import Path

from email_classifier.parse.mime import html_to_text, parse_raw

FIXTURES = Path(__file__).parent / "fixtures" / "eml"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestParsePlain:
    def test_from_and_subject(self) -> None:
        parsed = parse_raw(_read("plain_ham.eml"))
        assert parsed.sender_display_name == "Alice Example"
        assert parsed.sender_address == "alice@example.com"
        assert parsed.sender_domain == "example.com"
        assert parsed.subject == "Lunch tomorrow?"
        assert "meet at noon" in parsed.body_text
        assert parsed.has_attachments is False


class TestParseHtml:
    def test_strips_tags_and_scripts(self) -> None:
        parsed = parse_raw(_read("html_with_links.eml"))
        assert "alert" not in parsed.body_text
        assert "<a" not in parsed.body_text
        assert "deals" in parsed.body_text

    def test_collects_hrefs(self) -> None:
        parsed = parse_raw(_read("html_with_links.eml"))
        assert any("shop.example.com/deals" in u for u in parsed.urls)
        assert any("cdn.example.net" in u for u in parsed.urls)


class TestHtmlToText:
    def test_empty(self) -> None:
        assert html_to_text("") == ""

    def test_script_removed(self) -> None:
        text = html_to_text("<p>hi</p><script>evil()</script>")
        assert "hi" in text
        assert "evil" not in text


class TestAttachments:
    def test_detects_pdf_attachment(self) -> None:
        parsed = parse_raw(_read("multipart_attachment.eml"))
        assert parsed.has_attachments is True
        assert "invoice.pdf" in parsed.attachment_filenames
        assert "invoice attached" in parsed.body_text


class TestReplyTo:
    def test_reply_to_domain(self) -> None:
        parsed = parse_raw(_read("from_reply_to_mismatch.eml"))
        assert parsed.sender_domain == "paypal.example.com"
        assert parsed.reply_to_domain == "unrelated-domain.test"
        assert parsed.reply_to_address == "helpdesk@unrelated-domain.test"
