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
        laps: int,
        speed_left: float,
        speed_right: float,
        detail: str,
        status: str,
        controls: Sequence[tuple[str, str]],
    ) -> None:
        stats = Table.grid(padding=(0, 2))
        stats.add_row("[bold]Mode[/bold]", mode)
        if mode == "LINE-FOLLOWER":
            stats.add_row("[bold]Laps[/bold]", str(laps))
        stats.add_row("[bold]Speed (L/R)[/bold]", f"{speed_left:+.0f}% / {speed_right:+.0f}%")
        stats.add_row("[bold]" + ("Segment" if mode == "LINE-FOLLOWER" else "Boost") + "[/bold]", detail)
        stats.add_row("[bold]Status[/bold]", status)

        controls_table = Table(title="Controls", show_header=False, title_style="bold")
        for label, action in controls:
            controls_table.add_row(f"[bold]{label}[/bold]", action)

        self._live.update(Group(stats, "", controls_table))
