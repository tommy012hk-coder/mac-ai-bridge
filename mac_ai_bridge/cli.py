"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys

from .automation import APPS, BridgeError, ask
from .server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mac-ai-bridge",
        description="Use AI apps already signed in on this Mac.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    ask_parser = commands.add_parser("ask", help="send a prompt to a local app")
    ask_parser.add_argument("app", choices=sorted(APPS))
    ask_parser.add_argument("prompt")
    serve_parser = commands.add_parser("serve", help="start the loopback HTTP bridge")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    if args.command == "ask":
        try:
            print(ask(args.app, args.prompt))
        except BridgeError as exc:
            print(f"mac-ai-bridge: {exc}", file=sys.stderr)
            return 1
        return 0

    try:
        serve(args.host, args.port)
    except (OSError, ValueError) as exc:
        print(f"mac-ai-bridge: {exc}", file=sys.stderr)
        return 1
    return 0
