"""Entry point: claims-mcp-server CLI.

Runs the claims MCP server over stdio or HTTP (SPEC 5, SPEC 11).
Validates configuration at startup (SPEC S10).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from claims_mcp.config import ConfigError, load_config, validate_config
from claims_mcp.security import KeyStore
from claims_mcp.server import create_server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="claims_mcp",
        description="Read-only MCP server for health-insurance claims.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport to use: stdio (default) or http",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    transport = args.transport

    try:
        config = load_config()
        validate_config(config, transport=transport)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    key_store = None
    if transport == "http" and config.keys_file is not None:
        try:
            key_store = KeyStore.load(Path(config.keys_file))
        except Exception as exc:
            print(f"Failed to load keys file: {exc}", file=sys.stderr)
            return 1

    server = create_server(config, key_store=key_store)

    try:
        if transport == "http":
            server.run(
                transport="streamable-http",
                host=config.http_host,
                port=config.http_port,
            )
        else:
            server.run(transport="stdio")
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
