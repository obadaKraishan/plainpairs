"""The ``plainpairs`` command line."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from plainpairs import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plainpairs",
        description="Build a research corpus of how US medicine labels are worded for two readers.",
    )
    parser.add_argument("--version", action="version", version=f"plainpairs {__version__}")
    parser.add_subparsers(dest="command")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return 0  # pragma: no cover - every subcommand returns from its own handler
