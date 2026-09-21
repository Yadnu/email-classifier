"""Link-domain extraction. Counts and domains are computed in Python."""
from __future__ import annotations

from urllib.parse import urlparse


def domain_from_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("mailto:"):
        addr = raw.split(":", 1)[1]
        if "@" in addr:
            return addr.split("@", 1)[1].split("?")[0].lower()
        return ""
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def dedupe_link_domains(urls: list[str]) -> list[str]:
    """Return unique link hostnames in first-seen order. Empty hosts dropped."""
    seen: set[str] = set()
    domains: list[str] = []
    for url in urls:
        host = domain_from_url(url)
        if not host or host in seen:
            continue
        seen.add(host)
        domains.append(host)
    return domains
