# claims-mcp-server

> Status: in progress

Read-only MCP server over a synthetic health-insurance claims database: named parameterized tools, API-key auth, audit log, threat model.

## Quickstart

```bash
uv sync
uv run python scripts/seed_db.py --out data/claims.db
uv run python -m claims_mcp --transport stdio
```
