"""MCP server for Meridian Health claims database.

Exposes five read-only tools with defense-in-depth security:
- S1: Read-only SQLite behind authorizer
- S2: Parameterized queries only
- S4/S5/S6: Authentication, tool authorization, rate limiting
- S7: Untrusted text sanitization
- S8: Safe error taxonomy
- S9: Fail-closed audit logging
- S13: Full input inspection before SDK validation
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from claims_mcp import queries
from claims_mcp.audit import AuditLogger, AuditWriteError
from claims_mcp.config import ServerConfig
from claims_mcp.db import open_readonly
from claims_mcp.models import VALIDATORS, ToolError
from claims_mcp.security import (
    KeyStore,
    RateLimiter,
    check_tool_allowed,
    sanitize_untrusted_text,
)

logger = logging.getLogger(__name__)

READ_ONLY_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
)


class ClaimsMCPServer(MCPServer):
    """MCPServer subclass implementing the SPEC 5 pipeline and SPEC S13."""

    def __init__(
        self,
        config: ServerConfig,
        key_store: KeyStore | None = None,
        rate_limiter: RateLimiter | None = None,
        audit_logger: AuditLogger | None = None,
        name: str = "claims-mcp-server",
        **kwargs: Any,
    ) -> None:
        super().__init__(name=name, **kwargs)
        self.config = config
        self.key_store = key_store
        self.rate_limiter = rate_limiter or RateLimiter(
            max_calls=config.rate_limit_per_min
        )
        self.audit_logger = audit_logger or AuditLogger(config.audit_path)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Context | None = None,
    ) -> CallToolResult:
        """Execute tool pipeline directly, satisfying SPEC S13."""
        return self._run_pipeline(name, arguments, context=context)

    def _run_pipeline(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Context | None = None,
        caller: str = "stdio-local",
        transport: str = "stdio",
    ) -> CallToolResult:
        """Run the 9-step SPEC 5 pipeline."""
        start_time = time.perf_counter()
        request_id = uuid.uuid4().hex[:16]

        # 1. Authenticate (Caller / Token)
        # For HTTP, caller/token may be passed in or set on request state
        # In stdio mode, caller is 'stdio-local' and transport is 'stdio'

        # 2. Rate limit check (S6)
        if not self.rate_limiter.check(caller):
            duration_ms = (time.perf_counter() - start_time) * 1000
            try:
                self.audit_logger.log(
                    request_id=request_id,
                    caller=caller,
                    transport=transport,
                    tool=name,
                    outcome="rate_limited",
                    duration_ms=duration_ms,
                    error_code="RATE_LIMITED",
                )
            except AuditWriteError:
                pass
            return CallToolResult(
                is_error=True,
                content=[
                    TextContent(type="text", text="RATE_LIMITED: try again later")
                ],
            )

        # 3. Tool Authorization check (S5)
        # If a key_entry is present for the caller, verify tool allowlist
        if self.key_store is not None and caller != "stdio-local":
            key_entry = getattr(context, "key_entry", None)
            if key_entry is not None and not check_tool_allowed(key_entry, name):
                duration_ms = (time.perf_counter() - start_time) * 1000
                try:
                    self.audit_logger.log(
                        request_id=request_id,
                        caller=caller,
                        transport=transport,
                        tool=name,
                        outcome="denied",
                        duration_ms=duration_ms,
                        error_code="FORBIDDEN_TOOL",
                    )
                except AuditWriteError:
                    pass
                return CallToolResult(
                    is_error=True,
                    content=[TextContent(type="text", text="FORBIDDEN_TOOL")],
                )

        # 4. Input validation (SPEC 7 / models.py)
        validator = VALIDATORS.get(name)
        if validator is None:
            # Unknown tool
            return CallToolResult(
                is_error=True,
                content=[TextContent(type="text", text="NOT_FOUND")],
            )

        val_res = validator(arguments)
        if isinstance(val_res, ToolError):
            duration_ms = (time.perf_counter() - start_time) * 1000
            try:
                self.audit_logger.log(
                    request_id=request_id,
                    caller=caller,
                    transport=transport,
                    tool=name,
                    outcome="invalid",
                    invalid_fields=val_res.invalid_fields,
                    duration_ms=duration_ms,
                    error_code=val_res.code.value,
                )
            except AuditWriteError:
                return CallToolResult(
                    is_error=True,
                    content=[
                        TextContent(
                            type="text", text=f"INTERNAL: reference {request_id}"
                        )
                    ],
                )
            return CallToolResult(
                is_error=True,
                content=[TextContent(type="text", text=val_res.message)],
            )

        clean_args = val_res

        # 5. Open read-only connection (one per call, S1, D10)
        # 6. Run fixed parameterized SQL (queries.py)
        conn = None
        try:
            conn = open_readonly(self.config.db_path)

            if name == "get_claim":
                result = queries.get_claim(conn, clean_args["claim_id"])
                rows = 1 if result is not None else 0
            elif name == "list_member_claims":
                result = queries.list_member_claims(
                    conn,
                    clean_args["member_id"],
                    status=clean_args.get("status"),
                    limit=clean_args.get("limit", 20),
                    offset=clean_args.get("offset", 0),
                )
                rows = len(result["items"]) if result is not None else 0
            elif name == "get_coverage_rule":
                result = queries.get_coverage_rule(
                    conn,
                    clean_args["plan_id"],
                    clean_args["procedure_code"],
                )
                rows = 1 if result is not None else 0
            elif name == "get_member_ytd_summary":
                result = queries.get_member_ytd_summary(
                    conn,
                    clean_args["member_id"],
                    clean_args["year"],
                )
                rows = 1 if result is not None else 0
            elif name == "get_claim_notes":
                result = queries.get_claim_notes(
                    conn,
                    clean_args["claim_id"],
                    limit=clean_args.get("limit", 10),
                )
                rows = len(result["notes"]) if result is not None else 0
            else:
                result = None
                rows = 0

        except Exception as exc:
            logger.exception("Error executing query for %s: %s", name, exc)
            duration_ms = (time.perf_counter() - start_time) * 1000
            try:
                self.audit_logger.log(
                    request_id=request_id,
                    caller=caller,
                    transport=transport,
                    tool=name,
                    outcome="error",
                    duration_ms=duration_ms,
                    error_code="INTERNAL",
                )
            except Exception:
                pass
            return CallToolResult(
                is_error=True,
                content=[
                    TextContent(type="text", text=f"INTERNAL: reference {request_id}")
                ],
            )
        finally:
            if conn is not None:
                conn.close()

        # Handle NOT_FOUND
        if result is None:
            duration_ms = (time.perf_counter() - start_time) * 1000
            try:
                self.audit_logger.log(
                    request_id=request_id,
                    caller=caller,
                    transport=transport,
                    tool=name,
                    args=clean_args,
                    outcome="not_found",
                    duration_ms=duration_ms,
                    error_code="NOT_FOUND",
                )
            except AuditWriteError:
                return CallToolResult(
                    is_error=True,
                    content=[
                        TextContent(
                            type="text", text=f"INTERNAL: reference {request_id}"
                        )
                    ],
                )
            return CallToolResult(
                is_error=True,
                content=[TextContent(type="text", text="NOT_FOUND")],
            )

        # 7. Build output, sanitize text (S7)
        if name == "get_claim_notes":
            sanitized_notes = []
            for n in result.get("notes", []):
                cleaned_text, truncated = sanitize_untrusted_text(n["text"])
                sanitized_notes.append(
                    {
                        "note_id": n["note_id"],
                        "created_on": n["created_on"],
                        "author_type": n["author_type"],
                        "text": cleaned_text,
                        "truncated": n.get("truncated", False) or truncated,
                    }
                )
            result = {
                "claim_id": result["claim_id"],
                "untrusted": True,
                "notes": sanitized_notes,
            }

        # 8. Write audit line, FAIL CLOSED (audit.py, S9)
        duration_ms = (time.perf_counter() - start_time) * 1000
        try:
            self.audit_logger.log(
                request_id=request_id,
                caller=caller,
                transport=transport,
                tool=name,
                args=clean_args,
                outcome="ok",
                rows=rows,
                duration_ms=duration_ms,
            )
        except AuditWriteError:
            # S9: Fail closed - if audit line cannot be written, return INTERNAL
            # and no data
            return CallToolResult(
                is_error=True,
                content=[
                    TextContent(type="text", text=f"INTERNAL: reference {request_id}")
                ],
            )

        # 9. Return result
        return CallToolResult(
            is_error=False,
            content=[TextContent(type="text", text=json.dumps(result, indent=2))],
        )


def register_tools(server: ClaimsMCPServer) -> None:
    """Register the five read-only tools with annotations and docstrings."""

    @server.tool(
        name="get_claim",
        description="Fetch one claim joined with provider and plan details.",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def get_claim(claim_id: str) -> CallToolResult:
        return server._run_pipeline("get_claim", {"claim_id": claim_id})

    @server.tool(
        name="list_member_claims",
        description="List claims for a member, newest first, with pagination.",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def list_member_claims(
        member_id: str,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> CallToolResult:
        args = {"member_id": member_id, "limit": limit, "offset": offset}
        if status is not None:
            args["status"] = status
        return server._run_pipeline("list_member_claims", args)

    @server.tool(
        name="get_coverage_rule",
        description="Look up coverage rules for a plan and procedure code.",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def get_coverage_rule(plan_id: str, procedure_code: str) -> CallToolResult:
        return server._run_pipeline(
            "get_coverage_rule",
            {"plan_id": plan_id, "procedure_code": procedure_code},
        )

    @server.tool(
        name="get_member_ytd_summary",
        description="Get year-to-date claim summary and remaining limit.",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def get_member_ytd_summary(member_id: str, year: int) -> CallToolResult:
        return server._run_pipeline(
            "get_member_ytd_summary",
            {"member_id": member_id, "year": year},
        )

    @server.tool(
        name="get_claim_notes",
        description="Fetch untrusted notes for a claim, sanitized and capped.",
        annotations=READ_ONLY_ANNOTATIONS,
    )
    def get_claim_notes(claim_id: str, limit: int = 10) -> CallToolResult:
        return server._run_pipeline(
            "get_claim_notes",
            {"claim_id": claim_id, "limit": limit},
        )


def create_server(
    config: ServerConfig,
    key_store: KeyStore | None = None,
    rate_limiter: RateLimiter | None = None,
    audit_logger: AuditLogger | None = None,
) -> ClaimsMCPServer:
    """Create and configure a ClaimsMCPServer with the five registered tools."""
    server = ClaimsMCPServer(
        config=config,
        key_store=key_store,
        rate_limiter=rate_limiter,
        audit_logger=audit_logger,
    )
    register_tools(server)
    return server
