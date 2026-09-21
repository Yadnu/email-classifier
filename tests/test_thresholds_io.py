from pathlib import Path

from email_classifier.config import load_config
from email_classifier.api.thresholds_io import write_thresholds


def test_write_thresholds_keeps_comments(tmp_path: Path) -> None:
    dest = tmp_path / "config.yaml"
    dest.write_text(Path("config.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    current = load_config(dest).thresholds
    payload = {
        "phishing_category_confidence": current.phishing_category_confidence,
        "phishing_credential_request": current.phishing_credential_request,
        "phishing_brand_impersonation": current.phishing_brand_impersonation,
        "spam_is_spam": 0.91,
        "spam_category_confidence": current.spam_category_confidence,
        "promotional_action": current.promotional_action,
        "uncertain_floor": current.uncertain_floor,
        "needs_reply_label": current.needs_reply_label,
    }
    write_thresholds(payload, dest)
    text = dest.read_text(encoding="utf-8")
    assert "spam_is_spam: 0.91" in text
    assert "is_spam Noul threshold" in text
    assert load_config(dest).thresholds.spam_is_spam == 0.91
