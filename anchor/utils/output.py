"""Shared Rich console instances and output helpers."""

from rich.console import Console

out = Console()
err = Console(stderr=True)


def success(msg: str) -> None:
    out.print(f"[green]✓[/green] {msg}")


def error(msg: str) -> None:
    err.print(f"[red]✗[/red] {msg}")


def warn(msg: str) -> None:
    err.print(f"[yellow]![/yellow] {msg}")


def info(msg: str) -> None:
    out.print(f"[blue]→[/blue] {msg}")
