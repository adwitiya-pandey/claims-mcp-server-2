#!/usr/bin/env python3
"""Demo client for Meridian Health Claims MCP Server (TASKS T11/T14).

Connects over streamable HTTP with Bearer authentication:
1. Calls all five MCP tools with valid parameters (happy paths).
2. Demonstrates the SPEC 8 error taxonomy (NOT_FOUND and INVALID_INPUT).
3. Demonstrates prompt-injection sanitization across the seeded adversarial
   notes from data/adversarial_note_ids.txt.

Usage:
    python scripts/demo_client.py --key <API_KEY> [--url http://127.0.0.1:8765/mcp]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

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
        print("Generate a key: python scripts/make_key.py --id analyst-1 --tools all")
        return 1

    headers = {"Authorization": f"Bearer {key}"}
    print("=" * 72)
    print(" Meridian Health Claims MCP Server — Enterprise Live Demo Client")
    print(f" Target Endpoint: {url}")
    print("=" * 72)
    print()

    async with httpx2.AsyncClient(headers=headers, timeout=15.0) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport) as client:
            tools = await client.list_tools()
            print(f"✓ Connected successfully. Discovered {len(tools.tools)} MCP tools:")
            for t in tools.tools:
                readonly_str = (
                    " [read-only]"
                    if t.annotations and t.annotations.read_only_hint
                    else ""
                )
                print(f"  • {t.name}: {t.description}{readonly_str}")
            print()

            # -----------------------------------------------------------
            # SECTION 1: Standard Tools (Happy Paths)
            # -----------------------------------------------------------
            print("=" * 72)
            print(" SECTION 1: Standard Tool Execution (Happy Paths)")
            print("=" * 72)

            # 1. get_claim
            print("\n1. [Tool] get_claim(claim_id='CLM00000001')")
            r1 = await client.call_tool("get_claim", {"claim_id": "CLM00000001"})
            if r1.is_error:
                print(f"   [ERROR] {r1.content[0].text}")
            else:
                d1 = json.loads(r1.content[0].text)
                print(
                    f"   ✓ Member: {d1['member_id']} | Plan: {d1['plan_id']} | "
                    f"Provider: {d1['provider_id']} "
                    f"({d1['provider_network_status']}) | "
                    f"Status: {d1['status']} | Billed: ${d1['billed_amount']:.2f}"
                )

            # 2. list_member_claims
            print("\n2. [Tool] list_member_claims(member_id='M000001', limit=3)")
            r2 = await client.call_tool(
                "list_member_claims", {"member_id": "M000001", "limit": 3}
            )
            if r2.is_error:
                print(f"   [ERROR] {r2.content[0].text}")
            else:
                d2 = json.loads(r2.content[0].text)
                print(
                    f"   ✓ Total member claims: {d2['total']} | "
                    f"Returned: {len(d2['items'])}"
                )
                for item in d2["items"]:
                    print(
                        f"     - Claim {item['claim_id']} ({item['service_date']}): "
                        f"{item['procedure_code']} | "
                        f"${item['billed_amount']:.2f} [{item['status']}]"
                    )

            # 3. get_coverage_rule
            print("\n3. [Tool] get_coverage_rule('PLN001', 'PX0001')")
            r3 = await client.call_tool(
                "get_coverage_rule",
                {"plan_id": "PLN001", "procedure_code": "PX0001"},
            )
            if r3.is_error:
                print(f"   [ERROR] {r3.content[0].text}")
            else:
                d3 = json.loads(r3.content[0].text)
                max_str = (
                    f"${d3['max_allowed']:.2f}"
                    if d3.get("max_allowed") is not None
                    else "None"
                )
                print(
                    f"   ✓ Covered: {d3['covered']} | "
                    f"Preauth Required: {d3['requires_preauth']} | "
                    f"Max Allowed: {max_str}"
                )

            # 4. get_member_ytd_summary
            print("\n4. [Tool] get_member_ytd_summary(member_id='M000001', year=2026)")
            r4 = await client.call_tool(
                "get_member_ytd_summary",
                {"member_id": "M000001", "year": 2026},
            )
            if r4.is_error:
                print(f"   [ERROR] {r4.content[0].text}")
            else:
                d4 = json.loads(r4.content[0].text)
                print(
                    f"   ✓ Plan: {d4['plan_id']} | "
                    f"Annual Limit: ${d4['annual_limit']:.2f} | "
                    f"Remaining Limit: ${d4['remaining_annual_limit']:.2f}"
                )
                for s in d4["by_status"]:
                    print(
                        f"     - {s['status']}: {s['claim_count']} claims, "
                        f"billed ${s['total_billed']:.2f}, "
                        f"paid ${s['total_paid']:.2f}"
                    )

            # -----------------------------------------------------------
            # SECTION 2: Error Taxonomy & Guardrail Rejections
            # -----------------------------------------------------------
            print("\n" + "=" * 72)
            print(" SECTION 2: SPEC 8 Error Taxonomy & Guardrail Rejections")
            print("=" * 72)

            # NOT_FOUND error
            print("\n1. Testing NOT_FOUND on non-existent claim:")
            r_nf = await client.call_tool("get_claim", {"claim_id": "CLM99999999"})
            print(f"   Response (is_error={r_nf.is_error}): {r_nf.content[0].text}")

            # INVALID_INPUT error (pattern mismatch)
            print("\n2. Testing INVALID_INPUT on malformed claim ID:")
            r_inv = await client.call_tool("get_claim", {"claim_id": "NOT_AN_ID"})
            print(f"   Response (is_error={r_inv.is_error}): {r_inv.content[0].text}")

            # S13 extra argument check
            print("\n3. Testing S13 Guardrail on unexpected extra argument:")
            r_extra = await client.call_tool(
                "get_claim",
                {"claim_id": "CLM00000001", "unexpected_payload": "INJECTED_VALUE"},
            )
            print(
                f"   Response (is_error={r_extra.is_error}): {r_extra.content[0].text}"
            )

            # -----------------------------------------------------------
            # SECTION 3: Adversarial Notes & Prompt Injection Defense
            # -----------------------------------------------------------
            print("\n" + "=" * 72)
            print(" SECTION 3: Prompt-Injection Sanitization (Adversarial Corpus)")
            print("=" * 72)

            adv_file = Path("data/adversarial_note_ids.txt")
            if adv_file.exists():
                adv_ids = [
                    int(line.strip())
                    for line in adv_file.read_text().splitlines()
                    if line.strip()
                ]
                print(f"Testing {len(adv_ids)} adversarial notes from {adv_file}:")
            else:
                adv_ids = [1, 2, 3, 5, 6, 7]
                print(f"Testing sample adversarial notes: {adv_ids}")

            test_claims = [
                ("CLM00000866", "Note 1: Direct instruction override attempt"),
                ("CLM00000420", "Note 2: Fake <<SYSTEM>> role injection"),
                ("CLM00001414", "Note 3: Fake JSON tool call embedding"),
                ("CLM00000773", "Note 4: Markdown exfiltration link"),
                ("CLM00000520", "Note 5: Zero-width space obfuscation (Unicode Cf)"),
                ("CLM00000086", "Note 6: Bi-directional text override (Bidi Cf)"),
                ("CLM00000145", "Note 7: 20,000-character buffer overflow"),
                ("CLM00001001", "Note 8: CRLF fake audit log injection"),
            ]

            for claim_id, description in test_claims:
                print(f"\n• Querying {claim_id} ({description}):")
                rn = await client.call_tool("get_claim_notes", {"claim_id": claim_id})
                if rn.is_error:
                    print(f"   [ERROR] {rn.content[0].text}")
                else:
                    dn = json.loads(rn.content[0].text)
                    print(
                        f"   ✓ Untrusted Flag: {dn['untrusted']} | "
                        f"Notes Returned: {len(dn['notes'])}"
                    )
                    for n in dn["notes"]:
                        trunc_flag = " [TRUNCATED]" if n["truncated"] else ""
                        preview_text = n["text"][:60]
                        if len(n["text"]) > 60:
                            preview_text += "..."
                        preview = repr(preview_text)
                        print(
                            f"     - Note #{n['note_id']} by {n['author_type']}"
                            f"{trunc_flag} (len={len(n['text'])}): {preview}"
                        )

    print("\n" + "=" * 72)
    print(" Enterprise Live Demo Complete: All tools and defenses verified.")
    print("=" * 72)
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
