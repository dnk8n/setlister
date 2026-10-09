"""Progress for the long steps: a live bar with count, ETA and the current item on a
terminal, or a plain line every few items when output goes to a log file."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from typing import TypeVar

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

T = TypeVar("T")


def track(
    items: Iterable[T],
    label: str,
    console: Console,
    describe: Callable[[T], str] | None = None,
) -> Iterator[T]:
    items = list(items)
    total = len(items)
    if not total:
        return
    if console.is_terminal:
        columns = (
            TextColumn("  {task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TextColumn("left"),
            TimeRemainingColumn(),
            TextColumn("[dim]{task.fields[now]}"),
        )
        with Progress(*columns, console=console, transient=False) as bar:
            task = bar.add_task(label, total=total, now="")
            for item in items:
                bar.update(task, now=_short(describe(item)) if describe else "")
                yield item
                bar.advance(task)
        return
    # Not a terminal: one line about every 10% so a log shows steady progress.
    start = time.monotonic()
    every = max(1, total // 10)
    for n, item in enumerate(items, 1):
        yield item
        if n % every == 0 or n == total:
            spent = time.monotonic() - start
            left = spent / n * (total - n)
            now = f" · {_short(describe(item))}" if describe else ""
            console.print(
                f"  {label} {n}/{total} · {_mmss(spent)} spent, ~{_mmss(left)} left{now}",
                highlight=False,
            )


def _short(text: str, width: int = 50) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _mmss(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"
