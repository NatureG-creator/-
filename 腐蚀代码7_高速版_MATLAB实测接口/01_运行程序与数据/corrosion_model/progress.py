"""Lightweight progress helpers for long-running corrosion simulations."""

from __future__ import annotations

from typing import Callable


ProgressTarget = bool | Callable[[str], None] | None


def emit_progress(target: ProgressTarget, message: str) -> None:
    """Print or forward a progress message without touching numeric logic."""
    if callable(target):
        target(message)
        return
    if target:
        print(message, flush=True)


def report_progress(target: ProgressTarget, prefix: str, message: str) -> None:
    """Emit a formatted progress line with a stable prefix."""
    emit_progress(target, f"[{prefix}] {message}")


def should_report(step: int, total: int, segments: int = 20) -> bool:
    """Throttle loop progress so large runs stay readable.

    - 小循环：每一步都报。
    - 大循环：默认约 5% 报一次，同时首尾必报。
    """
    if total <= 0:
        return False
    if step <= 1 or step >= total:
        return True
    if total <= segments:
        return True
    interval = max(1, total // segments)
    return step % interval == 0
