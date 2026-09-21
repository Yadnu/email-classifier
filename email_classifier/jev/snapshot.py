"""Serialize the pinned Jev question map for the inspect API (not sent to logs)."""
from __future__ import annotations

from typing import Any

from typesafe_sdk import Choice, Noul, Score

from email_classifier.jev.questions import QUESTIONS


def snapshot_questions() -> list[dict[str, Any]]:
    """JSON-safe copy of instructions, types, and criteria."""
    items: list[dict[str, Any]] = []
    for name, question in QUESTIONS.items():
        if isinstance(question, Choice):
            items.append(
                {
                    "name": name,
                    "type": "Choice",
                    "instructions": question.instructions,
                    "criteria": dict(question.criteria),
                }
            )
        elif isinstance(question, Noul):
            items.append(
                {
                    "name": name,
                    "type": "Noul",
                    "instructions": question.instructions,
                }
            )
        elif isinstance(question, Score):
            items.append(
                {
                    "name": name,
                    "type": "Score",
                    "instructions": question.instructions,
                    "criteria": list(question.criteria),
                }
            )
        else:  # pragma: no cover
            items.append({"name": name, "type": type(question).__name__})
    return items
