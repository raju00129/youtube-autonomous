"""Shared generation progress helpers (Celery PROGRESS meta + optional callbacks)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

ProgressFn = Callable[[int, str], None]


def clamp_percent(value: int | float) -> int:
    return max(0, min(100, int(value)))


def kling_poll_percent(*, elapsed: float, timeout: float, status: str) -> int:
    """Map Kling async poll status + time into a 5–88% range while waiting."""
    st = (status or "").lower()
    if st in {"submitted", "pending", "queued"}:
        base = 8
    elif st in {"processing", "running", "in_progress"}:
        base = 18
    else:
        base = 12
    # Creep toward 88% as we wait (never hit 100 until download/compose finishes)
    frac = min(1.0, max(0.0, elapsed / max(timeout, 1.0)))
    return clamp_percent(base + frac * 70)


def report(cb: ProgressFn | None, percent: int, message: str) -> None:
    if cb:
        cb(clamp_percent(percent), message)


def celery_progress(task: Any, percent: int, message: str, **extra: Any) -> None:
    """Update Celery task state for GET /jobs/{id} polling."""
    meta = {"percent": clamp_percent(percent), "message": message, **extra}
    try:
        task.update_state(state="PROGRESS", meta=meta)
    except Exception:  # noqa: BLE001
        pass
