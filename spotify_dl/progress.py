"""Terminal progress bars for spotify-dl.

Thin wrapper around ``rich.progress`` that provides a context-managed
progress bar for the search and download phases of the pipeline.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

if TYPE_CHECKING:
    from rich.progress import TaskID

_STATUS_STYLES: dict[str, str] = {
    "done": "green",
    "found": "green",
    "skipped": "yellow",
    "failed": "red",
}


class ProgressBar:
    """A context-managed progress bar for tracking pipeline phases.

    Usage::

        with ProgressBar(total=10, description="Downloading") as bar:
            for track in tracks:
                # ... process track ...
                bar.log(f"  [1/10] Title ... done")
                bar.advance("Artist - Title", status="done")
    """

    def __init__(
        self,
        total: int,
        description: str = "Downloading",
        *,
        color: str = "blue",
        show_eta: bool = True,
    ) -> None:
        self._total = total
        self._description = description
        self._color = color
        self._show_eta = show_eta
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None

    def _build_progress(self) -> Progress:
        columns = [
            SpinnerColumn(),
            TextColumn(f"[bold {self._color}]{{task.description}}"),
            BarColumn(bar_width=None),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
        ]
        if self._show_eta:
            columns += [TextColumn("•"), TimeRemainingColumn()]
        columns.append(TextColumn("{task.fields[current_track]}", style="dim"))
        return Progress(*columns, expand=True)

    def advance(self, label: str, *, status: str = "done") -> None:
        """Mark one item as completed and update the bar."""
        if self._progress is not None and self._task_id is not None:
            style = _STATUS_STYLES.get(status, "white")
            display = f"[{style}]{status}[/{style}]: {label}"
            self._progress.update(self._task_id, advance=1, current_track=display)

    def log(self, message: str) -> None:
        """Print a message above the progress bar without disrupting it."""
        if self._progress is not None:
            self._progress.console.print(message, highlight=False)

    def __enter__(self) -> ProgressBar:
        self._progress = self._build_progress()
        self._progress.start()
        self._task_id = self._progress.add_task(
            self._description,
            total=self._total,
            current_track="",
        )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._progress is not None:
            self._progress.stop()
            self._progress = None
            self._task_id = None
