"""In-process fan-out for GET /api/live (SSE). Not persisted, not logged."""
from __future__ import annotations

import json
import queue
import threading
from typing import Any, Iterator

_lock = threading.Lock()
_subscribers: list[queue.Queue[str]] = []


def publish_classification(event: dict[str, Any]) -> None:
    payload = json.dumps(event, ensure_ascii=False)
    with _lock:
        targets = list(_subscribers)
    for q in targets:
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass


def subscribe() -> queue.Queue[str]:
    q: queue.Queue[str] = queue.Queue(maxsize=256)
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue[str]) -> None:
    with _lock:
        if q in _subscribers:
            _subscribers.remove(q)


def sse_lines(q: queue.Queue[str], *, heartbeat_s: float = 15.0) -> Iterator[str]:
    try:
        while True:
            try:
                payload = q.get(timeout=heartbeat_s)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            yield f"data: {payload}\n\n"
    finally:
        unsubscribe(q)
