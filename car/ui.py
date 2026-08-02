"""Shared rich console and styled output helpers, so every module prints consistently."""

from collections.abc import Sequence

from rich.console import Console, Group
from rich.live import Live
from rich.table import Table

console = Console()


def banner(title: str) -> None:
    console.rule(f"[bold cyan]{title}[/bold cyan]")


def success(message: str) -> None:
    console.print(f"[bold green]✓[/bold green] {message}")


def error(message: str) -> None:
    console.print(f"[bold red]✗ {message}[/bold red]")


def _format_lap_time(seconds: float | None) -> str:
    if seconds is None:
        return "\u2013"
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes}:{secs:04.1f}"


def _lap_color(last: float, best: float) -> str:
    if last <= best:
        return "bold green"  # new PB or tied
    if last <= best * 1.1:
        return "yellow"
    return "red"


class Dashboard:
    """An in-place-updating status line for real-time stats (laps, speed, mode, ...).

    Runtime-only, in-memory stats like these change every tick; printing them with plain
    console.print() would scroll a new line each time, so this uses rich's Live display to redraw
    the same line instead. Regular console.print()/success()/error() calls (using the same
    console) still work normally while a Dashboard is active — rich prints them above the
    in-place-updating line rather than disrupting it.
    """

    def __init__(self) -> None:
        self._live = Live(console=console, refresh_per_second=10, transient=False)

    def __enter__(self) -> "Dashboard":
        self._live.__enter__()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._live.__exit__(*exc_info)

    def update(
        self,
        *,
        mode: str,
        speed_left: float,
        speed_right: float,
        detail: str,
        detail_label: str = "Boost",
        status: str,
        controls: Sequence[tuple[str, str]],
        laps: int | None = None,
        lap_elapsed: float | None = None,
        last_lap_time: float | None = None,
        best_lap_time: float | None = None,
    ) -> None:
        stats = Table.grid(padding=(0, 2))
        stats.add_row("[bold]Mode[/bold]", mode)
        if laps is not None:
            stats.add_row("[bold]Laps[/bold]", str(laps))
            stats.add_row("[bold]Current lap[/bold]", _format_lap_time(lap_elapsed))
            last_str = _format_lap_time(last_lap_time)
            if last_lap_time is not None and best_lap_time is not None:
                last_str = f"[{_lap_color(last_lap_time, best_lap_time)}]{last_str}[/]"
            stats.add_row("[bold]Last lap[/bold]", last_str)
            best_str = "[bold green]" + _format_lap_time(best_lap_time) + "[/]" if best_lap_time is not None else "\u2013"
            stats.add_row("[bold]Best lap[/bold]", best_str)
        stats.add_row("[bold]Speed (L/R)[/bold]", f"{speed_left:+.0f}% / {speed_right:+.0f}%")
        stats.add_row(f"[bold]{detail_label}[/bold]", detail)
        stats.add_row("[bold]Status[/bold]", status)

        controls_table = Table(title="Controls", show_header=False, title_style="bold")
        for label, action in controls:
            controls_table.add_row(f"[bold]{label}[/bold]", action)

        self._live.update(Group(stats, "", controls_table))
