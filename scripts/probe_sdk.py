"""Re-run MCP SDK probe snippets from docs/mcp_sdk_notes.md."""

import asyncio

from mcp import Client
from mcp.server import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

srv = MCPServer("probe")


@srv.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False))
def typed(claim_id: str) -> dict:
    if claim_id == "boom":
        raise ValueError("NOT_FOUND")
    return {"ok": True}


@srv.tool()
def returns_error(x: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text="INVALID_INPUT: claim_id is invalid")],
        is_error=True,
    )


@srv.tool()
def loose(claim_id: object = None) -> dict:
    return {"got": type(claim_id).__name__}


async def main():
    async with Client(srv) as c:
        result = await c.list_tools()
        tools = result.tools
        print(f"Tools listed: {len(tools)}")
        for t in tools:
            ann = t.annotations
            print(f"  {t.name}: annotations={ann}")

        for name, args in [
            ("typed", {"claim_id": "hello"}),
            ("typed", {"claim_id": "boom"}),
            ("typed", {"wrong": 1}),
            ("returns_error", {"x": "a"}),
            ("loose", {"claim_id": 123}),
            ("loose", {"extra": 1}),
            ("loose", {}),
        ]:
            r = await c.call_tool(name, args)
            texts = [getattr(x, "text", x) for x in r.content][:1]
            print(f"{name} {args} -> is_error={r.is_error} text={texts}")


asyncio.run(main())
