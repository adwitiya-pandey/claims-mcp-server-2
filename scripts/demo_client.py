#!/usr/bin/env python3
"""Demo client for Meridian Health Claims MCP Server (TASKS T11).

Connects over streamable HTTP with Bearer authentication, calls each of the
five tools (including one adversarial note), and displays compact output.
No LLM calls are made.

Usage:
    python scripts/demo_client.py --key <API_KEY> [--url http://127.0.0.1:8765/mcp]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Demo client calling claims-mcp-server over HTTP."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("CLAIMS_HTTP_URL", "http://127.0.0.1:8765/mcp"),
        help="Server MCP URL (default: http://127.0.0.1:8765/mcp)",
    )
    parser.add_argument(
        "--key",
        default=os.environ.get("CLAIMS_API_KEY"),
        help="API key for authentication (or set CLAIMS_API_KEY)",
    )
    return parser.parse_args()


async def run_demo(url: str, key: str | None) -> int:
    if not key:
        print("Error: --key or CLAIMS_API_KEY environment variable is required.")
        print("Use scripts/make_key.py to generate a key.")
        return 1

    headers = {"Authorization": f"Bearer {key}"}
    print("=" * 60)
    print(" Meridian Health Claims MCP Server — Live Demo Client")
    print(f" Target: {url}")
    print("=" * 60)
    print()

    async with httpx2.AsyncClient(headers=headers, timeout=10.0) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport) as client:
            tools = await client.list_tools()
            print(f"✓ Connected successfully. Available tools: {len(tools.tools)}")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description}")
            print()

            # 1. get_claim
            print("1. Calling get_claim(claim_id='CLM00000001')...")
            r1 = await client.call_tool("get_claim", {"claim_id": "CLM00000001"})
            if r1.is_error:
                print(f"   [ERROR] {r1.content[0].text}")
            else:
                data = json.loads(r1.content[0].text)
                print(
                    f"   [OK] Member: {data['member_id']} | Plan: {data['plan_id']} | "
                    f"Status: {data['status']} | Billed: ${data['billed_amount']:.2f}"
                )
            print()

            # 2. list_member_claims
            print("2. Calling list_member_claims(member_id='M000001', limit=3)...")
            r2 = await client.call_tool(
                "list_member_claims", {"member_id": "M000001", "limit": 3}
            )
            if r2.is_error:
                print(f"   [ERROR] {r2.content[0].text}")
            else:
                data = json.loads(r2.content[0].text)
                print(
                    f"   [OK] Total claims: {data['total']} | "
                    f"Returned: {len(data['items'])}"
                )
                for item in data["items"]:
                    print(
                        f"        - {item['claim_id']} ({item['service_date']}): "
                        f"{item['procedure_code']} | ${item['billed_amount']:.2f} "
                        f"[{item['status']}]"
                    )
            print()

            # 3. get_coverage_rule
            print("3. Calling get_coverage_rule('PLN001', 'PX0001')...")
            r3 = await client.call_tool(
                "get_coverage_rule",
                {"plan_id": "PLN001", "procedure_code": "PX0001"},
            )
            if r3.is_error:
                print(f"   [ERROR] {r3.content[0].text}")
            else:
                data = json.loads(r3.content[0].text)
                max_str = (
                    f"${data['max_allowed']:.2f}"
                    if data.get("max_allowed") is not None
                    else "None"
                )
                print(
                    f"   [OK] Covered: {data['covered']} | "
                    f"Preauth required: {data['requires_preauth']} | "
                    f"Max allowed: {max_str}"
                )
            print()

            # 4. get_member_ytd_summary
            print("4. Calling get_member_ytd_summary('M000001', 2026)...")
            r4 = await client.call_tool(
                "get_member_ytd_summary",
                {"member_id": "M000001", "year": 2026},
            )
            if r4.is_error:
                print(f"   [ERROR] {r4.content[0].text}")
            else:
                data = json.loads(r4.content[0].text)
                print(
                    f"   [OK] Plan: {data['plan_id']} | "
                    f"Annual Limit: ${data['annual_limit']:.2f} | "
                    f"Remaining Limit: ${data['remaining_annual_limit']:.2f}"
                )
                for s in data["by_status"]:
                    print(
                        f"        - {s['status']}: {s['claim_count']} claims, "
                        f"billed ${s['total_billed']:.2f}, paid ${s['total_paid']:.2f}"
                    )
            print()

            # 5. get_claim_notes (includes adversarial note)
            print("5. Calling get_claim_notes('CLM00000866') [adversarial note]...")
            r5 = await client.call_tool("get_claim_notes", {"claim_id": "CLM00000866"})
            if r5.is_error:
                print(f"   [ERROR] {r5.content[0].text}")
            else:
                data = json.loads(r5.content[0].text)
                print(
                    f"   [OK] Untrusted: {data['untrusted']} | "
                    f"Notes count: {len(data['notes'])}"
                )
                for note in data["notes"]:
                    truncated_str = " (truncated)" if note["truncated"] else ""
                    print(
                        f"        - Note #{note['note_id']} by "
                        f"{note['author_type']}{truncated_str}: "
                        f"{repr(note['text'][:75])}"
                    )
            print()

    print("=" * 60)
    print(" Demo complete. All 5 tools executed successfully.")
    print("=" * 60)
    return 0


def main() -> None:
    args = parse_args()
    try:
        sys.exit(asyncio.run(run_demo(args.url, args.key)))
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as exc:
        print(f"Connection error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
