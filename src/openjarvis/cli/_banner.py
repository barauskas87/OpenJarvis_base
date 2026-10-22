"""Startup banner — Tradelit wordmark + tagline."""

from __future__ import annotations

# "Tradelit" rendered in the figlet "standard" font. Stored as plain text
# (no inline Rich markup) so the backslashes in the glyphs don't collide with
# Rich's [tag] markup or Python raw-string escaping — colour is applied at
# print time via a style argument.
_WORDMARK = (
    " _____              _      _ _ _   ",
    "|_   _| __ __ _  __| | ___| (_) |_ ",
    "  | || '__/ _` |/ _` |/ _ \\ | | __|",
    "  | || | | (_| | (_| |  __/ | | |_ ",
    "  |_||_|  \\__,_|\\__,_|\\___|_|_|\\__|",
)

_TAGLINE = "Personal AI, On Personal Devices"


def print_banner(quiet: bool = False) -> None:
    """Print the Tradelit startup banner. No-op when quiet."""
    if quiet:
        return
    try:
        from rich.console import Console

        console = Console()
        for line in _WORDMARK:
            console.print(line, style="bold bright_blue", highlight=False, markup=False)
        console.print(f"      {_TAGLINE}", style="cyan", highlight=False, markup=False)
        console.print()
    except ImportError:
        for line in _WORDMARK:
            print(line)
        print(f"      {_TAGLINE}")
        print()
