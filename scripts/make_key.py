#!/usr/bin/env python3
"""Generate an API key and append its hash to keys.json.

Usage:
    python scripts/make_key.py --id analyst-1 --tools all
    python scripts/make_key.py --id triage-bot --tools get_claim,list_member_claims
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

from claims_mcp.security import hash_key

VALID_TOOLS = {
    "all",
    "get_claim",
    "list_member_claims",
    "get_coverage_rule",
    "get_member_ytd_summary",
    "get_claim_notes",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an API key")
    parser.add_argument("--id", required=True, help="Key identifier (e.g., analyst-1)")
    parser.add_argument(
        "--tools",
        required=True,
        help="Comma-separated tool names, or 'all'",
    )
    parser.add_argument(
        "--keys-file",
        default="keys.json",
        help="Path to keys.json (default: keys.json)",
    )
    args = parser.parse_args()

    tools = [t.strip() for t in args.tools.split(",")]
    for t in tools:
        if t not in VALID_TOOLS:
            print(f"Error: unknown tool '{t}'", file=sys.stderr)
            print(f"Valid tools: {', '.join(sorted(VALID_TOOLS))}", file=sys.stderr)
            sys.exit(1)

    # Generate a secure random key
    raw_key = secrets.token_urlsafe(32)
    key_hash = hash_key(raw_key)

    # Load or create keys.json
    keys_path = Path(args.keys_file)
    if keys_path.exists():
        data = json.loads(keys_path.read_text())
    else:
        data = {"keys": []}

    # Check for duplicate key_id
    for entry in data["keys"]:
        if entry["key_id"] == args.id:
            print(f"Error: key_id '{args.id}' already exists", file=sys.stderr)
            sys.exit(1)

    data["keys"].append(
        {
            "key_id": args.id,
            "sha256": key_hash,
            "allowed_tools": tools,
        }
    )

    keys_path.write_text(json.dumps(data, indent=2) + "\n")

    # Print the plaintext key ONCE — never stored
    print(f"Key ID:    {args.id}")
    print(f"Raw key:   {raw_key}")
    print(f"SHA-256:   {key_hash}")
    print(f"Tools:     {', '.join(tools)}")
    print(f"Saved to:  {keys_path}")
    print()
    print("⚠ The raw key above is printed once and never stored.")
    print("  Save it securely now.")


if __name__ == "__main__":
    main()
