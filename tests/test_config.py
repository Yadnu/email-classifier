"""Tests for email_classifier.config."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from email_classifier.config import AppConfig, load_config


class TestLoadConfig:
    def test_defaults_when_no_file(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "missing.yaml")
        assert cfg.ingest.batch_size == 10
        assert cfg.jev.model == "jev-1.13.0"
        assert cfg.thresholds.uncertain_floor == 0.50

    def test_overrides_from_yaml(self, tmp_path: Path) -> None:
        data = {
            "ingest": {"batch_size": 10, "promotions_as": "ham"},
            "jev": {"model": "jev-2.0.0"},
        }
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump(data))
        cfg = load_config(cfg_file)
        assert cfg.ingest.batch_size == 10
        assert cfg.ingest.promotions_as == "ham"
        assert cfg.jev.model == "jev-2.0.0"
        # Untouched defaults remain.
        assert cfg.thresholds.uncertain_floor == 0.50

    def test_partial_override(self, tmp_path: Path) -> None:
        data = {"thresholds": {"spam_is_spam": 0.90}}
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump(data))
        cfg = load_config(cfg_file)
        assert cfg.thresholds.spam_is_spam == 0.90
        # Other thresholds keep defaults.
        assert cfg.thresholds.phishing_category_confidence == 0.85

    def test_empty_yaml_uses_defaults(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "empty.yaml"
        cfg_file.write_text("")
        cfg = load_config(cfg_file)
        assert isinstance(cfg, AppConfig)
        assert cfg.jev.price_per_million_input_tokens == 0.042
