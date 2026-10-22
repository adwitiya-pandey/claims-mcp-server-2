# AGENTS.md

> **AUTONOMOUS END-TO-END EXECUTION RULE (SINGLE-CHAT WORKFLOW)**:
> Execute **all tasks in `TASKS.md` back-to-back from `T0`/`H0` through `v0.1.0` GitHub push** in a single continuous run.
> - **Do NOT stop after individual tasks** to wait for human PR merges. Commit each task cleanly with Conventional Commits (`Refs: <TaskID>`), merge branches automatically, update `PROGRESS.md`, and continue straight to the next task.
> - **Write 100% of the code yourself** (including `queries.py`, `graph.py`, `policy.py`, `approvals.py`, `sqlsafe.py`, and the `H9` merge conflict).
> - **API Keys**: Use `GEMINI_API_KEY` from the project's `.env` file for live Gemini steps. Never require `ANTHROPIC_API_KEY` or `LANGSMITH_API_KEY`.


Read SPEC.md (the contract), the TASKS.md task you were given, and the SPEC sections that task cites, before touching code. This file holds only what is not obvious from the code.

## What this is
A read-only MCP server over a synthetic health-insurance claims SQLite database. Five named tools, auth, per-tool authorization, rate limiting, audit log. Python 3.12, `uv`. No LLM calls anywhere in this repo.

## Environment and commands
- The owner works in WSL2 Ubuntu (repo under `~/projects`, never under `/mnt/c` or `/mnt/d`) and sometimes opens it from Windows. CI runs Linux. Use `pathlib`; never hard-code path separators or shell-specific syntax in code or tests. Line endings are LF (`.gitattributes`).
- Install: `uv sync`
- Check: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
- Run each task's own acceptance command from TASKS.md before committing.
- Run only the commands above, the task's own commands, and `git`/`gh` for the task's branch and PR. Ask before anything else.

## Gotchas that will bite you
1. **The MCP Python SDK is v2** (verified: `mcp` 2.3.0). `FastMCP` and `mcp.server.fastmcp` do not exist; use `MCPServer`. `docs/mcp_sdk_notes.md` holds the verified imports and probe results: re-run its probes against the installed version before writing MCP code, and correct the file if anything differs. Never invent an SDK API.
2. **The SDK validates typed handler arguments before your handler runs**, and its error text echoes the raw input. That would skip auth, rate limiting and the audit line, and leak input. SPEC S13 requires a test first; see `docs/mcp_sdk_notes.md`.
3. **Tool errors are returned, not raised**: `CallToolResult(is_error=True, content=[TextContent(...)])` with the exact SPEC 8 text. A raised exception loses its message ("Error executing tool X"). Project B parses this format.
4. **Regex:** use `re.fullmatch` with `[0-9]`. `\d` matches non-ASCII digits, and `$` matches before a trailing newline.
5. **SQLite read-only:** open with a URI built by `Path.resolve().as_uri() + "?mode=ro"` and `uri=True`. Without `mode=ro`, a missing path silently creates an empty database. Set `PRAGMA query_only=ON` before installing the authorizer (the authorizer blocks PRAGMA).
6. **Threads:** the SDK runs plain `def` handlers in worker threads, and SQLite connections are not thread-safe by default. Open one read-only connection per call and close it.
7. **Logs:** never write result payloads, note text, or raw invalid input to the audit log or stdout. Log field names only for invalid calls.

## Never
- Write all 5 parameterized SQL functions in `src/claims_mcp/queries.py` in T5b using `?` placeholders and explain each query in `docs/EXPLAIN-PLAIN-ENGLISH.md`.
- Never add a tool that accepts SQL, table, column or ORDER BY input. Never add write tools.
- Never print or commit `.env` (keep `.env` in `.gitignore`; load it automatically via `python-dotenv` / `pydantic-settings`), `keys.json`, `*.db` or `audit/`. Secrets reach the process only as environment variables the owner sets. Never print a plaintext key except in `make_key.py` once.
- Never use real personal data, even in examples. All data is synthetic.
- Never change tool names, contracts, error codes or security requirements to make a test pass. Fix the code, or stop and ask.
- Never skip or weaken a security test.

## Work style: autonomous, with a short list of reasons to stop
- One task per branch (`task/T4-readonly-db`), one task per chat session. Your first message: the task ID, the files you will touch, the tests you will write first, the acceptance command. Keep it short, then proceed.
- Commits follow Conventional Commits: `type(scope): imperative summary`, at most 72 characters, no task ID in the subject. Types: `feat`, `fix`, `test`, `docs`, `ci`, `chore`, `refactor`. Put `Refs: T4` as a trailer. Example: `feat(db): open SQLite read-only behind an authorizer`.
- Commit with a conventional title (`Refs: T<N>`), merge into `main` automatically, and proceed immediately to the next task. Do not ask permission for routine work.
- Two-step git in any instructions you write for the owner: `git branch <name>` then `git switch <name>`; never `git checkout -b`.
- Facts only from official docs (https://py.sdk.modelcontextprotocol.io, uv, pytest, ruff, SQLite) and the installed packages.

**Stop and ask the owner before:**
- adding or upgrading any dependency not listed in SPEC;
- changing SPEC.md, a tool contract, an error code, or a security requirement;
- any network access other than package installs and reading official docs;
- deleting or renaming files outside the current task's scope;
- anything that weakens the read-only guarantee, auth, or the audit trail.

If SPEC is ambiguous, choose the safest reading, record the question in `docs/open_questions.md`, and continue.

## Definition of done for every task
The acceptance command in TASKS.md passes; ruff is clean; new behaviour has a test; `docs/decisions.md` is updated if a decision changed; the commit is small and described in plain words. End the PR body with three lines: what you changed, how it was verified, and what the owner should read to understand it.

## Harness
This file is read by VS Code Copilot (setting `chat.useAgentsMdFile`) and by Antigravity (1.20.5 or later). If it is not in your context, say so before doing anything else. Keep this file under 12,000 characters (Antigravity's per-rules-file limit).
