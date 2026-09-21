"""Load and expose the application configuration from config.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class GmailConfig:
    credentials_path: str = "data/credentials.json"
    token_path: str = "data/token.json"
    readonly_scopes: list[str] = field(
        default_factory=lambda: ["https://www.googleapis.com/auth/gmail.readonly"]
    )
    modify_scopes: list[str] = field(
        default_factory=lambda: ["https://www.googleapis.com/auth/gmail.modify"]
    )


@dataclass
class IngestConfig:
    db_path: str = "data/classifier.db"
    page_size: int = 500
    batch_size: int = 10
    # Pause between Gmail batch requests to stay under ~250 quota units/sec.
    batch_pause_s: float = 0.6
    max_retries: int = 6
    max_messages: Optional[int] = None
    promotions_as: str = "promotional"
    include_spam_trash: bool = True


@dataclass
class JevConfig:
    model: str = "jev-1.13.0"
    price_per_million_input_tokens: float = 0.042
    body_excerpt_chars: int = 1500


@dataclass
class ThresholdsConfig:
    phishing_category_confidence: float = 0.85
    phishing_credential_request: float = 0.80
    phishing_brand_impersonation: float = 0.80
    spam_is_spam: float = 0.75
    spam_category_confidence: float = 0.80
    promotional_action: float = 0.60
    uncertain_floor: float = 0.50
    needs_reply_label: float = 0.70


@dataclass
class StatsConfig:
    drift_alert_pct: float = 10.0


@dataclass
class AppConfig:
    gmail: GmailConfig = field(default_factory=GmailConfig)
    ingest: IngestConfig = field(default_factory=IngestConfig)
    jev: JevConfig = field(default_factory=JevConfig)
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    stats: StatsConfig = field(default_factory=StatsConfig)


def _merge_dataclass(instance: object, data: dict) -> None:
    """Recursively merge a dict into a dataclass instance."""
    for key, value in data.items():
        if not hasattr(instance, key):
            continue
        current = getattr(instance, key)
        if isinstance(value, dict) and hasattr(current, "__dataclass_fields__"):
            _merge_dataclass(current, value)
        else:
            setattr(instance, key, value)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load config.yaml into an AppConfig, using defaults for any missing keys."""
    config = AppConfig()
    config_path = Path(path)
    if config_path.exists():
        with config_path.open() as f:
            raw = yaml.safe_load(f) or {}
        _merge_dataclass(config, raw)
    return config


# Module-level singleton — import this everywhere.
# Re-load by calling load_config() explicitly.
_DEFAULT_CONFIG_PATH = os.environ.get("CLASSIFIER_CONFIG", "config.yaml")
cfg: AppConfig = load_config(_DEFAULT_CONFIG_PATH)
