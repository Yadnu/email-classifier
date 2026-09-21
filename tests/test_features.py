"""Tests for code-computed features. Fake .eml fixtures only."""
from __future__ import annotations

from pathlib import Path

from email_classifier.features.auth import parse_auth_results
from email_classifier.features.identity import from_reply_to_mismatch
from email_classifier.features.links import dedupe_link_domains, domain_from_url
from email_classifier.parse.mime import parse_raw

FIXTURES = Path(__file__).parent / "fixtures" / "eml"


class TestAuthResults:
    def test_parses_authentication_results(self) -> None:
        parsed = parse_raw((FIXTURES / "auth_headers.eml").read_bytes())
        auth = parse_auth_results(parsed.authentication_results, parsed.received_spf)
        assert auth.spf_result == "pass"
        assert auth.dkim_result == "pass"
        assert auth.dmarc_result == "pass"

    def test_received_spf_fallback(self) -> None:
        parsed = parse_raw((FIXTURES / "auth_fail_received_spf.eml").read_bytes())
        auth = parse_auth_results(parsed.authentication_results, parsed.received_spf)
        assert auth.spf_result == "fail"
        assert auth.dkim_result == "none"
        assert auth.dmarc_result == "none"

    def test_fail_from_auth_header(self) -> None:
        parsed = parse_raw((FIXTURES / "from_reply_to_mismatch.eml").read_bytes())
        auth = parse_auth_results(parsed.authentication_results, parsed.received_spf)
        assert auth.spf_result == "fail"
        assert auth.dkim_result == "fail"
        assert auth.dmarc_result == "fail"

    def test_empty_headers_are_none(self) -> None:
        auth = parse_auth_results("", "")
        assert auth.spf_result == "none"
        assert auth.dkim_result == "none"
        assert auth.dmarc_result == "none"


class TestLinkDomains:
    def test_strips_www_and_dedupes(self) -> None:
        urls = [
            "https://shop.example.com/deals",
            "https://www.shop.example.com/sale",
            "https://cdn.example.net/img.png",
            "https://shop.example.com/other",
        ]
        domains = dedupe_link_domains(urls)
        assert domains == ["shop.example.com", "cdn.example.net"]

    def test_mailto(self) -> None:
        assert domain_from_url("mailto:a@example.com") == "example.com"

    def test_empty(self) -> None:
        assert dedupe_link_domains([]) == []


class TestIdentity:
    def test_mismatch(self) -> None:
        assert from_reply_to_mismatch("paypal.example.com", "unrelated-domain.test") is True

    def test_same_domain(self) -> None:
        assert from_reply_to_mismatch("example.com", "example.com") is False

    def test_missing_reply_to_is_not_mismatch(self) -> None:
        assert from_reply_to_mismatch("example.com", "") is False
