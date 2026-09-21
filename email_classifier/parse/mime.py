"""Parse raw RFC 5322 bytes into structured fields.

Uses the stdlib ``email`` package for MIME and BeautifulSoup for HTML-to-text.
The body is treated as adversarial: it is never mixed into other fields.
"""
from __future__ import annotations

import email
import email.policy
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import parseaddr
from typing import Optional

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field


class ParsedEmail(BaseModel):
    """Structured result of MIME parsing. No Jev decisions live here."""

    sender_display_name: str = ""
    sender_address: str = ""
    sender_domain: str = ""
    reply_to_address: str = ""
    reply_to_domain: str = ""
    subject: str = ""
    date_header: str = ""
    authentication_results: str = ""
    received_spf: str = ""
    body_plain: str = ""
    body_html: str = ""
    body_text: str = ""
    urls: list[str] = Field(default_factory=list)
    has_attachments: bool = False
    attachment_filenames: list[str] = Field(default_factory=list)


def _decode_header_value(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _domain_of(address: str) -> str:
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[-1].strip().lower()


def _walk_parts(msg: Message) -> tuple[str, str, list[str], bool]:
    """Return (plain, html, attachment_filenames, has_attachments)."""
    plain_parts: list[str] = []
    html_parts: list[str] = []
    filenames: list[str] = []
    has_attachments = False

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            filename = part.get_filename()
            disposition = (part.get_content_disposition() or "").lower()
            if filename or disposition == "attachment":
                has_attachments = True
                if filename:
                    filenames.append(_decode_header_value(filename))
                continue
            _collect_body_part(part, plain_parts, html_parts)
    else:
        disposition = (msg.get_content_disposition() or "").lower()
        filename = msg.get_filename()
        if filename or disposition == "attachment":
            has_attachments = True
            if filename:
                filenames.append(_decode_header_value(filename))
        else:
            _collect_body_part(msg, plain_parts, html_parts)

    return "\n".join(plain_parts), "\n".join(html_parts), filenames, has_attachments


def _collect_body_part(part: Message, plain_parts: list[str], html_parts: list[str]) -> None:
    ctype = (part.get_content_type() or "").lower()
    payload = _decode_payload(part)
    if not payload:
        return
    if ctype == "text/plain":
        plain_parts.append(payload)
    elif ctype == "text/html":
        html_parts.append(payload)


def _decode_payload(part: Message) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            raw = part.get_payload()
            return raw if isinstance(raw, str) else ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:
        return ""


def html_to_text(html: str) -> str:
    """Strip tags and scripts; return visible text only."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_urls_from_html(html: str) -> list[str]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for tag in soup.find_all("a", href=True):
        href = (tag.get("href") or "").strip()
        if href:
            urls.append(href)
    return urls


def extract_urls_from_text(text: str) -> list[str]:
    """Pull http(s) URLs from plain text without a heavy regex library."""
    urls: list[str] = []
    lower = text
    i = 0
    while True:
        http = lower.find("http://", i)
        https = lower.find("https://", i)
        candidates = [p for p in (http, https) if p >= 0]
        if not candidates:
            break
        start = min(candidates)
        end = start
        while end < len(text) and text[end] not in " \t\r\n<>\"'":
            end += 1
        url = text[start:end].rstrip(").,;:]")
        if url:
            urls.append(url)
        i = end
    return urls


def parse_raw(raw_rfc822: bytes) -> ParsedEmail:
    """Parse raw RFC 5322 bytes into a ParsedEmail."""
    msg = email.message_from_bytes(raw_rfc822, policy=email.policy.default)
    if not isinstance(msg, Message):
        msg = EmailMessage()

    from_name, from_addr = parseaddr(_decode_header_value(msg.get("From")))
    reply_name, reply_addr = parseaddr(_decode_header_value(msg.get("Reply-To")))
    subject = _decode_header_value(msg.get("Subject"))

    auth_results = msg.get("Authentication-Results") or ""
    if isinstance(auth_results, list):
        auth_results = " ".join(str(x) for x in auth_results)
    received_spf = msg.get("Received-SPF") or ""

    plain, html, filenames, has_attachments = _walk_parts(msg)
    body_text = plain.strip() if plain.strip() else html_to_text(html)

    urls = extract_urls_from_html(html) + extract_urls_from_text(plain)
    # Dedup preserving order.
    seen: set[str] = set()
    unique_urls: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    return ParsedEmail(
        sender_display_name=from_name.strip(),
        sender_address=from_addr.strip().lower(),
        sender_domain=_domain_of(from_addr),
        reply_to_address=reply_addr.strip().lower(),
        reply_to_domain=_domain_of(reply_addr),
        subject=subject,
        date_header=_decode_header_value(msg.get("Date")),
        authentication_results=str(auth_results),
        received_spf=str(received_spf),
        body_plain=plain,
        body_html=html,
        body_text=body_text,
        urls=unique_urls,
        has_attachments=has_attachments,
        attachment_filenames=filenames,
    )
