"""Apply Jev-* labels via Gmail messages.modify (add only)."""
from __future__ import annotations

from typing import Any

from email_classifier.label.plan import ALLOWED_LABELS

_FORBIDDEN_MODIFY_KEYS = frozenset(
    {"removeLabelIds", "removeLabelids", "remove_label_ids"}
)


def list_label_names(service: Any) -> dict[str, str]:
    """Map label name → Gmail label id."""
    payload = service.users().labels().list(userId="me").execute()
    return {item["name"]: item["id"] for item in payload.get("labels", [])}


def ensure_allowed_labels(service: Any) -> dict[str, str]:
    """Create missing Jev-* labels. Never deletes or renames anything."""
    existing = list_label_names(service)
    for name in ALLOWED_LABELS:
        if name in existing:
            continue
        created = (
            service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        existing[name] = created["id"]
    return {name: existing[name] for name in ALLOWED_LABELS}


def add_labels(service: Any, message_id: str, label_ids: list[str]) -> None:
    """Add labels only. Raises if a caller tries to remove or trash."""
    if not label_ids:
        return
    body = {"addLabelIds": list(label_ids)}
    if _FORBIDDEN_MODIFY_KEYS & set(body):
        raise RuntimeError("refusing Gmail modify that would remove labels")
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body=body,
    ).execute()
