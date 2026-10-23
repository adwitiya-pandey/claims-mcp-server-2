# Architecture and Design Decisions

This document records the architectural and security decisions made for `claims-mcp-server`, matching SPEC 14 and the implementation.

| # | Decision | Rejected alternative | Why | Proven by |
|---|---|---|---|---|
| D1 | Five named, parameterized tools | A generic "run SQL" tool | Smaller attack surface; auditable | S2/S3 tests (`test_validation.py`, `test_queries.py`) |
| D2 | Read-only at the connection (`mode=ro`, `query_only`, authorizer) | A regex that checks for SELECT | Defense in depth; a regex is not a security boundary | `test_db_readonly.py` |
| D3 | SQLite behind `db.py` | Postgres now | No server in CI; swap later without touching tools | Config and structure |
| D4 | Audit log in a separate JSONL file | Audit table in the claims DB | The claims DB must stay read-only | S1, S9 tests (`test_audit.py`) |
| D5 | Audit write fails means no data returned | Best-effort logging | Compliance needs a trail for every access | `test_audit.py` |
| D6 | Untrusted text is sanitized, capped and flagged | Passing notes through raw | Reduces risk, labels data as data. It does NOT stop a model from obeying text | S7 tests (`test_security.py`) |
| D7 | Per-key tool allowlists | One all-powerful key | Least privilege | S5 tests (`test_security.py`) |
| D8 | Hashed keys at rest, constant-time compare | Plaintext keys in env | A leaked keys file is not a leaked credential | S4 tests (`test_security.py`) |
| D9 | stdio (local, no auth) plus HTTP (auth) | HTTP only | Inspector and local dev need stdio; auth is meaningless there | `test_config.py` |
| D10 | One read-only connection per call; handlers are plain `def` | Shared connection or pool | SQLite connections are not thread-safe by default and the SDK runs sync handlers in worker threads | `test_db_readonly.py`, `test_server_protocol.py` |
| D11 | In-memory fixed-window rate limit | Redis or token bucket | Single process; documented limitation | S6 tests (`test_security.py`) |
| D12 | Test-first parameterized SQL (`T5a` tests -> `T5b` implementation) | Unverified SQL | Guarantees contract compliance and zero SQL string interpolation | `test_queries.py` |
| D13 | Subclass `MCPServer` overriding `call_tool` to dispatch raw arguments through pipeline | Letting SDK validate parameters via Pydantic or untyped loose handlers | The MCP SDK v2 validates typed parameters before handler invocation and echoes raw input on validation error (`input_value={...}`). Overriding `call_tool` intercepts every incoming tool call before SDK Pydantic validation, routes it through the SPEC 5 pipeline (auth, rate limiting, audit, validation, read-only DB query, sanitization), and preserves full typed schemas and annotations in `list_tools()` | `test_s13_server.py`, `test_server_protocol.py` |
| D14 | Custom ASGI BearerAuthMiddleware wrapping the streamable HTTP app | SDK TokenVerifier / OAuthAuthorizationServerProvider | The SDK requires full OAuth and AuthSettings configuration for TokenVerifier. A lightweight ASGI middleware directly enforces constant-time Bearer token verification against the hashed KeyStore and returns HTTP 401 with an empty body on missing or invalid keys, cleanly isolating transport auth from MCP protocol handling | `test_server_protocol.py` |
