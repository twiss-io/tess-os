# `tessctl mcp serve` — selected Tess checks over MCP

MCP (Model Context Protocol) is an interoperability protocol used by many
clients, not a universal capability or a trust mechanism. `tessctl mcp serve`
exposes four existing checks (contract validation, the gate's verdict-coverage
ship-check, mission-record reads, roster reads) as MCP tools over a stdio
JSON-RPC 2.0 transport, so an agent can call them
**during a session** instead of only at the git pre-commit / pre-push / CI
boundary. It does not replace `tessctl gate install-hooks` — the git-boundary
enforcement stays exactly as it was (docs/GATE_QUICKSTART.md). This is an
additional, earlier checkpoint: an agent can ask "would this be blocked?"
before it ever stages a commit.

The server does not issue approvals, establish verifier trust, or make a
platform a certified Tess OS adapter. Only the Claude Code configuration path
is smoke-tested here; other client snippets need independent validation.

Protocol: [MCP 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18)
— JSON-RPC 2.0 messages, one per line, over stdin/stdout (the
[stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)).
Implementation: **stdlib-only** — no `mcp` SDK / pip dependency. This matches
tessctl's own stated runtime contract ("Python 3 (stdlib + pyyaml). No Node.
Self-contained single file.") — JSON-RPC over newline-delimited stdio needs
nothing beyond `json` and `sys.stdin`/`sys.stdout`.

Every tool below is a thin wrapper that calls tessctl's own EXISTING internal
functions — the same code the CLI commands call — never a re-implementation.
See the "MCP region" comment block in `.tess/bin/tessctl` (directly below the
Goal #6 RUN region) for the full implementation.

## Quickstart

```bash
# from the root of a Tess OS project (this repo, or one scaffolded from it)
./tessctl mcp serve
```

The process blocks, reading JSON-RPC requests from stdin and writing
responses to stdout, one JSON object per line, until stdin is closed (or you
Ctrl-D / Ctrl-C it). It's meant to be launched by an MCP client, not run
interactively — the quickstart above is just to confirm the binary starts
without an unhandled exception. Configure a client below instead.

## Configuring a client

### Claude Code — `.mcp.json`

Add a project-scoped entry (checked into the repo, per Claude Code's
[MCP docs](https://code.claude.com/docs/en/mcp)) at `.mcp.json` in your
project root:

```json
{
  "mcpServers": {
    "tessctl": {
      "command": "${CLAUDE_PROJECT_DIR:-.}/tessctl",
      "args": ["mcp", "serve"]
    }
  }
}
```

`CLAUDE_PROJECT_DIR` is set in the *spawned server's* environment by Claude
Code (not in Claude Code's own environment), which is why the `:-.`
fallback is required — see "Environment variable expansion in `.mcp.json`"
in the docs linked above. No `"type"` field is needed: an entry with a
`command` and no `url` is read as stdio by default. Claude Code prompts for
approval the first time a project-scoped server from `.mcp.json` is used
(`claude mcp list` / `claude mcp reset-project-choices` to manage that).

If you'd rather register it without hand-editing JSON:

```bash
claude mcp add-json tessctl '{"command":"'"$(pwd)"'/tessctl","args":["mcp","serve"]}' --scope project
```

### Codex CLI — `~/.codex/config.toml`

```toml
[mcp_servers.tessctl]
command = "/absolute/path/to/your/tess-os/tessctl"
args = ["mcp", "serve"]
```

Or interactively: `codex mcp add tessctl -- /absolute/path/to/tessctl mcp serve`.
Codex's config keys stdio servers under `[mcp_servers.<name>]`
([reference](https://developers.openai.com/codex/mcp)); there's no
project-root env var equivalent to Claude Code's `CLAUDE_PROJECT_DIR`, so use
an absolute path (`tessctl`'s own root-discovery reads `TESS_ROOT`/walks up
from its own script location via the bash wrapper, not from Codex's cwd, so
an absolute `command` path is all that's needed for correct root resolution).

### Gemini CLI — `settings.json`

```json
{
  "mcpServers": {
    "tessctl": {
      "command": "/absolute/path/to/your/tess-os/tessctl",
      "args": ["mcp", "serve"]
    }
  }
}
```

Gemini CLI's `mcpServers` block takes `command`/`args`/`env`/`cwd`/`timeout`/
`trust` per server
([reference](https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html)).
Set `"cwd"` to the project root if you'd rather use a relative `command`.

### Cursor

Cursor reads the same `mcpServers` shape as Claude Code's `.mcp.json`, either
in a project's `.cursor/mcp.json` or the user-level config — use the Claude
Code snippet above with an absolute `command` path (Cursor does not set a
`CLAUDE_PROJECT_DIR`-equivalent variable).

## The four tools

### `validate_contract`

Runs the same schema + relational-lint pass as `tessctl validate
<contract-type> <file>` (reuses `load_contract_schema` /
`load_contract_instance` / `schema_validate` / `_lint_contract` /
`classify_validation_infra_error` / `classify_schema_miss` verbatim).

| Field | Type | Required | Notes |
|---|---|---|---|
| `contract_type` | string | yes | one of `brief`, `crew-plan`, `verdict`, `return-manifest`, `mission`, `retry`, `policy` |
| `path` | string | one of `path`/`content` | resolved against the tess project root if relative |
| `content` | string | one of `path`/`content` | inline instance content — for a draft that isn't on disk yet |
| `format` | string | required with `content` | one of `json`, `yaml`, `yml`, `md` |

Result: `{valid, contract_type, file, violations[], classification?}` — the
exact shape `tessctl validate --json` prints, minus the CLI's exit code (a
schema-invalid contract is `valid: false`, not a protocol error).

### `gate_check_paths`

Runs the **same decision engine** as `tessctl gate pre-push` / `tessctl gate
ci` — it calls `_gate_run_ship_check()` directly, the exact shared function
both of those CLI subcommands call. The caller provides its claimed path set,
an immutable `base` commit ID, and a `head` ref/sha. The tool independently
derives the authoritative NUL-delimited raw Git diff, including status, modes,
and full object IDs. A duplicate, omitted, or invented caller path returns a
blocked `PATH_SET_MISMATCH` result; path-only agent input is never admission
authority.

Full 40- or 64-hex IDs are accepted here only as immutable raw Git ingress.
The current `verdict.artifact_hashes` contract remains SHA-1-only (40 hex), so
this tool cannot turn a governed SHA-256 blob into an approvable change; it
fails closed until a future schema migration explicitly defines that support.

`base` is not optional. It must be a full 40- or 64-hex commit ID, never a
branch, tag, or other mutable ref. The gate reads both verifier-registration
metadata and public-key bytes from that BASE tree; it will not fall back to a
candidate policy, candidate key file, or the current checkout. A missing or
mutable base returns a normal blocked result containing `BASE_REQUIRED`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `paths` | string[] | yes | claimed repo-relative paths; must exactly equal the immutable raw Git diff |
| `base` | string | yes | immutable full 40- or 64-hex base commit ID; mutable refs are rejected |
| `head` | string | no | git ref/sha; defaults to current `HEAD` |
| `verdict_dirs` | string[] | no | restrict covering-verdict discovery to these directories |

Result: `{blocked, reasons[], changed_paths[], base, head}` — identical shape
(plus the resolved `base`/`head`) to `tessctl gate pre-push --base X --head
Y --json`'s `result` for the same `changed_paths`/refs. See
`tests/test_mcp_serve.py` for the equivalence proof against a real fixture
repo (BLOCKED and ALLOWED cases), the path-set-substitution denial, and the
explicit no-base denial test.

### `mission_status`

Reads a mission record exactly like `tessctl mission status --json` (reuses
`_read_mission_record()` verbatim).

| Field | Type | Required |
|---|---|---|
| `mission_id` | string | yes |

Result: `{found, mission_id, record?, gates_cleared?, gates_total?, error?}`
— `found: false` (not a protocol error) for an unknown mission id.

### `roster_list`

Lists installed (core-managed, live) vs staged/benched agents — reuses
`load_lock()` + `_agent_keys_by_name()` verbatim (the same data `tessctl
roster list` prints as columns).

No arguments. Result: `{installed[], staged[], installed_count, staged_count}`.

## Protocol notes

- **Lifecycle**: `initialize` → client sends `notifications/initialized` →
  normal operation (`tools/list`, `tools/call`). `initialize` returns
  `protocolVersion: "2025-06-18"`, `capabilities.tools.listChanged: false`
  (the tool set is fixed at process start), and `serverInfo`.
- **Framing**: one JSON-RPC message per line, UTF-8, no embedded newlines —
  exactly the stdio transport spec. The server never writes anything to
  stdout that isn't a valid JSON-RPC message; use stderr for any future
  logging.
- **Errors**: a malformed request (bad JSON, unknown method, invalid
  `tools/call` params, unknown tool name) is a genuine JSON-RPC protocol
  error (`error.code`/`error.message`, standard codes: `-32700` parse error,
  `-32600` invalid request, `-32601` method not found, `-32602` invalid
  params, `-32603` internal error). A tool's own BUSINESS-LOGIC failure
  (e.g. a schema-invalid contract, an unknown mission id) is never a
  protocol error — it's a normal `tools/call` **result**, per the MCP spec's
  "Tool Execution Errors" ("Protocol Errors" vs "Tool Execution Errors" are
  deliberately different mechanisms).
- **Notifications** (no `id` field, e.g. `notifications/initialized`) never
  get a response, success or error — JSON-RPC 2.0 §4.1.
- Root discovery is identical to every other tessctl command:
  `find_tess_root()` (honours `TESS_ROOT`, else walks up from cwd for
  `tess.manifest.json`).

## What's genuinely working vs. v1 scope

Working, tested over real stdio pipes: the `initialize` → `tools/list` →
`tools/call` round trip; all four tools; `gate_check_paths`'s equivalence to
`gate pre-push`/`gate ci`, proven against a real git+GPG fixture in both the
BLOCKED and ALLOWED-with-covering-verdict directions; JSON-RPC error paths
(bad method, bad params, malformed JSON); the Claude Code `.mcp.json`
snippet, smoke-tested by spawning the server exactly as that config would.

Not built (deliberately out of v1 scope):

- **No `resources` or `prompts` capability** — tools only. `tools.listChanged`
  is `false`; the tool set never changes mid-process.
- **No batching validation beyond spec-completeness** — a batch (`[...]`)
  line is accepted and each item dispatched, but no MCP client observed in
  practice sends one; this is unexercised beyond a basic test.
- **No pagination** on `tools/list` (`cursor`/`nextCursor`) — four tools
  fit in one page; wire it if the tool count grows enough to matter.
- **No `logging`/`completions`/`sampling`/`elicitation` capabilities.**
- **The Codex/Gemini/Cursor config snippets are documented from each
  project's own reference docs, not smoke-tested against a real Codex/
  Gemini/Cursor install** (no such harness is available in this dev
  environment) — only the Claude Code `.mcp.json` path is spawn-tested
  here. The underlying server is protocol-generic (plain JSON-RPC 2.0 over
  stdio), so there's no tessctl-side reason it would behave differently
  under a different client, but that's an inference, not a proof.
