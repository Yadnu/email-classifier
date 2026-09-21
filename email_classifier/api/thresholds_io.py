"""Read/write threshold keys in config.yaml without dropping comments."""
from __future__ import annotations

import os
import re
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from email_classifier.config import ThresholdsConfig, load_config

THRESHOLD_KEYS = tuple(f.name for f in fields(ThresholdsConfig))


def config_path() -> Path:
    return Path(os.environ.get("CLASSIFIER_CONFIG", "config.yaml"))


def read_thresholds() -> dict[str, Any]:
    cfg = load_config(config_path())
    return asdict(cfg.thresholds)


def write_thresholds(values: dict[str, float], path: Path | None = None) -> dict[str, float]:
    target = path or config_path()
    if not target.exists():
        raise FileNotFoundError(str(target))
    cleaned: dict[str, float] = {}
    for key in THRESHOLD_KEYS:
        if key not in values:
            raise KeyError(key)
        val = float(values[key])
        if not 0.0 <= val <= 1.0:
            raise ValueError(f"{key} must be between 0 and 1")
        cleaned[key] = val
    text = target.read_text(encoding="utf-8")
    for key, val in cleaned.items():
        pattern = re.compile(rf"^([ \t]*{re.escape(key)}:[ \t]*)[0-9]+(?:\.[0-9]+)?", re.MULTILINE)
        text, n = pattern.subn(lambda m, v=val: f"{m.group(1)}{v:.2f}", text, count=1)
        if n != 1:
            raise ValueError(f"could not update {key} in {target}")
    target.write_text(text, encoding="utf-8")
    return cleaned
