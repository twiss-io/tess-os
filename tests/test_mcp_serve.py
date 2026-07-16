"""
Goal #9 — `tessctl mcp serve`: the gate as an MCP server (MCP region of
.tess/bin/tessctl, directly below the Goal #6 RUN region).

Spec: Model Context Protocol 2025-06-18 (JSON-RPC 2.0 over stdio, newline-
delimited framing — https://modelcontextprotocol.io/specification/2025-06-18).
docs/MCP.md documents the four tools + per-harness client config.

Coverage (per the dispatch brief's explicit acceptance list), all driven
over REAL stdio pipes (a genuine subprocess, not an in-process function
call), except where noted:
  * `initialize` -> `notifications/initialized` -> `tools/list` ->
    `tools/call` round trips, exactly the MCP lifecycle.
  * All four tools produce a `tools/call` result (validate_contract,
    gate_check_paths, mission_status, roster_list).
  * `gate_check_paths` is diagnostic-only: it always returns
    `authoritative: false`, `blocked: true`, and `MCP_DIAGNOSTIC_ONLY` even
    when the shared evaluator would allow the supplied paths. Invalid,
    same, reversed, and non-commit ranges are rejected before evaluation.
  * Error handling: bad JSON-RPC method, bad `tools/call` params (unknown
    tool name, missing required argument), and a malformed JSON line all
    return proper JSON-RPC protocol errors (-32601/-32602/-32700) — never
    a crashed session and never conflated with a tool's own business-logic
    failure (which is a normal result, not a protocol error).
  * A notification (`notifications/initialized`) never gets a response.
  * The documented Claude Code `.mcp.json` entry
    (`command: "${CLAUDE_PROJECT_DIR:-.}/tessctl"`, `args: ["mcp",
    "serve"]`) is smoke-tested by spawning the real bash wrapper exactly
    that way (env-var pre-resolved to the fixture root — Claude Code's own
    `${VAR}` expansion is its concern, not tessctl's).
  * `tessctl mcp serve` at the CLI level: clean exit 0 on stdin EOF; `tessctl
    mcp` with no subcommand refuses with a clear message.
"""

from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT, ENGINE_SRC  # noqa: F401  (ENGINE_SRC used indirectly via project fixture)

# Reuse the mission-ledger CLI helpers + minimal fixture (no duplication of
# an already-proven scaffold) — pytest.ini's `pythonpath = tests` makes
# every test module import-able, and this exact cross-import pattern is
# already used elsewhere in this suite (test_render_ordering_guard.py ->
# test_tracked_render_e2e.py).
from test_mission_ledger import mroot, _run as _mission_run, _mission_dir

# Reuse only the gate-spine's ordinary git helpers. The MCP boundary tests
# deliberately do not provision verifier keys or produce signed verdicts:
# an MCP caller can never establish authoritative event/remote provenance.
from test_gate_spine import _base_sha, _commit_all

CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"
WRAPPER_SRC = REPO_ROOT / "tessctl"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mcp_root(project):
    """A full synthetic project root (contracts copied in, tess.lock/
    tess.manifest.json written) ready to spawn `tessctl mcp serve` as a
    real subprocess and drive it over stdio."""
    shutil.copytree(CONTRACTS_SRC, project.root / "core" / "contracts")
    project.write()
    return project.root


@pytest.fixture
def wrapper_root(mcp_root):
    """`mcp_root` plus the real repo-root bash wrapper (`./tessctl`) copied
    in — lets a test spawn the server exactly the way the documented
    `.mcp.json` entry (`command: tessctl, args: [mcp, serve]`) would."""
    dst = mcp_root / "tessctl"
    shutil.copy2(WRAPPER_SRC, dst)
    os.chmod(dst, 0o755)
    return mcp_root


@pytest.fixture
def mcp_git_root(mcp_root):
    """A real git repo with the shipped policy and no verifier key setup.

    This fixture proves the MCP trust boundary without GPG: a valid ungated
    diff lets the shared evaluator report ``diagnostic_would_block: false``,
    while the MCP result itself must remain non-authoritative and blocked.
    """
    shutil.copytree(REPO_ROOT / "core" / "policy", mcp_root / "core" / "policy")
    subprocess.run(["git", "init", "-q", str(mcp_root)], check=True)
    subprocess.run(["git", "-C", str(mcp_root), "config", "user.email", "mcp@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(mcp_root), "config", "user.name", "MCP Test"], check=True)
    subprocess.run(["git", "-C", str(mcp_root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(mcp_root), "commit", "-q", "-m", "baseline"], check=True)
    return mcp_root


# ---------------------------------------------------------------------------
# A tiny real-stdio-pipes JSON-RPC client. Talks to a genuine `tessctl mcp
# serve` subprocess — not the in-process engine module — over its actual
# stdin/stdout pipes, exactly like a real MCP client would.
# ---------------------------------------------------------------------------

class McpStdio:
    def __init__(self, root: Path, *, use_wrapper: bool = False, extra_env: dict | None = None):
        env = {**os.environ, "TESS_ROOT": str(root)}
        if extra_env:
            env.update(extra_env)
        if use_wrapper:
            cmd = [str(root / "tessctl"), "mcp", "serve"]
        else:
            cmd = [sys.executable, str(root / ".tess" / "bin" / "tessctl"), "mcp", "serve"]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, cwd=str(root), env=env,
        )
        self._next_id = 0

    def _write_line(self, obj: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _read_line(self, timeout: float):
        assert self.proc.stdout is not None
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            return None
        line = self.proc.stdout.readline()
        return line if line != "" else None  # "" == EOF

    def request(self, method: str, params: dict | None = None, timeout: float = 15.0) -> dict:
        self._next_id += 1
        msg_id = self._next_id
        self._write_line({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}})
        line = self._read_line(timeout)
        assert line is not None, (
            f"no response to {method!r} within {timeout}s "
            f"(stderr so far: {self._drain_stderr()!r})"
        )
        resp = json.loads(line)
        assert resp.get("id") == msg_id, f"response id mismatch: {resp}"
        return resp

    def notify(self, method: str, params: dict | None = None) -> None:
        self._write_line({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def raw_line(self, text: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def read_one_line(self, timeout: float = 5.0):
        return self._read_line(timeout)

    def no_response_within(self, timeout: float = 0.5) -> bool:
        return self._read_line(timeout) is None

    def _drain_stderr(self) -> str:
        try:
            ready, _, _ = select.select([self.proc.stderr], [], [], 0.2)
            if ready:
                return self.proc.stderr.read(4096)
        except Exception:
            pass
        return ""

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def _initialize(client: McpStdio) -> dict:
    resp = client.request(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest-mcp-client", "version": "0.0.1"},
        },
    )
    client.notify("notifications/initialized")
    return resp


# ---------------------------------------------------------------------------
# 1) Lifecycle round trip: initialize -> initialized -> tools/list -> tools/call
# ---------------------------------------------------------------------------

def test_lifecycle_round_trip_over_real_stdio_pipes(mcp_root):
    client = McpStdio(mcp_root)
    try:
        init_resp = _initialize(client)
        assert init_resp["result"]["protocolVersion"] == "2025-06-18"
        assert init_resp["result"]["serverInfo"]["name"] == "tessctl"
        assert init_resp["result"]["capabilities"]["tools"]["listChanged"] is False

        list_resp = client.request("tools/list")
        tools = {t["name"]: t for t in list_resp["result"]["tools"]}
        assert set(tools.keys()) == {
            "validate_contract", "gate_check_paths", "mission_status", "roster_list",
        }
        for spec in tools.values():
            assert spec["inputSchema"]["type"] == "object"
            assert "description" in spec and spec["description"]

        call_resp = client.request("tools/call", {"name": "roster_list", "arguments": {}})
        result = call_resp["result"]
        assert result["isError"] is False
        assert "content" in result and result["content"][0]["type"] == "text"
        payload = json.loads(result["content"][0]["text"])
        assert payload == result["structuredContent"]
        assert "installed" in payload and "staged" in payload
    finally:
        client.close()


def test_notification_never_gets_a_response(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)  # already sends one notification; prove no stray reply arrived
        assert client.no_response_within(0.5)

        client.notify("notifications/initialized")  # a second, redundant notification
        assert client.no_response_within(0.5)

        # The pipe is still alive and answers a REAL request afterward.
        resp = client.request("tools/list")
        assert "tools" in resp["result"]
    finally:
        client.close()


def test_ping_is_answered(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("ping")
        assert resp["result"] == {}
    finally:
        client.close()


# ---------------------------------------------------------------------------
# 2) Error handling — proper JSON-RPC protocol errors
# ---------------------------------------------------------------------------

def test_unknown_method_returns_method_not_found(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("totally/bogus")
        assert "error" in resp
        assert resp["error"]["code"] == -32601
    finally:
        client.close()


def test_tools_call_unknown_tool_returns_invalid_params(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {"name": "no_such_tool", "arguments": {}})
        assert "error" in resp
        assert resp["error"]["code"] == -32602
    finally:
        client.close()


def test_tools_call_missing_required_argument_returns_invalid_params(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {"name": "validate_contract", "arguments": {}})
        assert "error" in resp
        assert resp["error"]["code"] == -32602
        assert "contract_type" in resp["error"]["message"]
    finally:
        client.close()


def test_tools_call_missing_params_name_returns_invalid_params(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {"arguments": {}})
        assert resp["error"]["code"] == -32602
    finally:
        client.close()


def test_malformed_json_line_returns_parse_error(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        client.raw_line("{not valid json")
        line = client.read_one_line(timeout=5.0)
        assert line is not None
        resp = json.loads(line)
        assert resp["error"]["code"] == -32700
        assert resp["id"] is None

        # The server is still alive and answers the next real request.
        resp2 = client.request("tools/list")
        assert "tools" in resp2["result"]
    finally:
        client.close()


def test_invalid_request_non_object_message_is_rejected(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        client.raw_line(json.dumps("just a string"))
        line = client.read_one_line(timeout=5.0)
        resp = json.loads(line)
        assert resp["error"]["code"] == -32600
    finally:
        client.close()


def test_business_logic_failure_is_a_normal_result_not_a_protocol_error(mcp_root):
    """A schema-invalid contract is NOT a JSON-RPC error — per the spec's
    'Tool Execution Errors' vs 'Protocol Errors' split, it's a completely
    normal tools/call RESULT with valid: false."""
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request(
            "tools/call",
            {
                "name": "validate_contract",
                "arguments": {
                    "contract_type": "brief",
                    "content": "not: a-brief\n",
                    "format": "yaml",
                },
            },
        )
        assert "error" not in resp
        result = resp["result"]
        assert result["isError"] is False
        payload = result["structuredContent"]
        assert payload["valid"] is False
        assert payload["violations"]
    finally:
        client.close()


# ---------------------------------------------------------------------------
# 3) validate_contract
# ---------------------------------------------------------------------------

_VALID_BRIEF = {
    "objective": "Quantify where in the funnel conversion is dropping, stage by stage.",
    "output_contract": "/tmp/conv-analysis.md — sections [Funnel table, Drop-off stage, Evidence]",
    "tools_sources_constraints": "Read the CRM export at /data/crm.csv; every number traces to a quoted row.",
    "not_responsible_for": "Recommending fixes (that is stage 2).",
    "milestones": [],
    "escalation_trigger": "Export missing -> stop, surface to conductor.",
    "prod_touching": False,
    "estimated_minutes": 10,
}


_EXTERNAL_RETURN_MANIFEST = {
    "task_id": "task1",
    "mission_id": "m1",
    "agent": "test-agent",
    "status": "complete",
    "self_reported_complete": True,
    "artifacts": [{"path": "/etc/hosts", "description": "external host file"}],
    "claims": [{"claim": "done", "evidence": "none", "inferred": False}],
    "flags": [],
}


def test_validate_contract_inline_content_valid(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "validate_contract",
            "arguments": {"contract_type": "brief", "content": json.dumps(_VALID_BRIEF), "format": "json"},
        })
        payload = resp["result"]["structuredContent"]
        assert payload["valid"] is True, payload["violations"]
        assert payload["violations"] == []
    finally:
        client.close()


def test_validate_contract_inline_return_manifest_rejects_external_artifact(mcp_root):
    """MCP validation shares the CLI/gate containment rule, not CWD state."""
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "validate_contract",
            "arguments": {
                "contract_type": "return-manifest",
                "content": json.dumps(_EXTERNAL_RETURN_MANIFEST),
                "format": "json",
            },
        })
        payload = resp["result"]["structuredContent"]
        assert payload["valid"] is False
        assert any("absolute" in violation for violation in payload["violations"])
    finally:
        client.close()


def test_validate_contract_path_based(mcp_root):
    brief_path = mcp_root / "missions" / "m1" / "briefs" / "task1.brief.json"
    brief_path.parent.mkdir(parents=True)
    brief_path.write_text(json.dumps(_VALID_BRIEF), encoding="utf-8")

    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "validate_contract",
            "arguments": {"contract_type": "brief", "path": "missions/m1/briefs/task1.brief.json"},
        })
        payload = resp["result"]["structuredContent"]
        assert payload["valid"] is True, payload["violations"]
        assert payload["file"].endswith("task1.brief.json")
    finally:
        client.close()


def test_validate_contract_path_schema_errors_redact_repository_values(mcp_root):
    secret = "SENSITIVE-REPOSITORY-VALUE-MUST-NOT-ECHO"
    brief = dict(_VALID_BRIEF, destructive=False, step=secret)
    brief_path = mcp_root / "missions" / "m1" / "briefs" / "redact.brief.json"
    brief_path.parent.mkdir(parents=True)
    brief_path.write_text(json.dumps(brief), encoding="utf-8")

    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "validate_contract",
            "arguments": {
                "contract_type": "brief",
                "path": "missions/m1/briefs/redact.brief.json",
            },
        })
        payload = resp["result"]["structuredContent"]
        assert payload["valid"] is False
        assert payload["violations"] == [
            "contract schema violation 1 (repository value details redacted)"
        ]
        assert secret not in json.dumps(resp)
    finally:
        client.close()


def test_validate_contract_rejects_absolute_path_outside_repository(mcp_root):
    secret = "OUTSIDE-REPOSITORY-CONTENT-MUST-NOT-ECHO"
    outside = mcp_root.parent / f"{mcp_root.name}-outside.brief.json"
    outside.write_text(json.dumps(dict(_VALID_BRIEF, step=secret)), encoding="utf-8")

    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "validate_contract",
            "arguments": {"contract_type": "brief", "path": str(outside)},
        })
        payload = resp["result"]["structuredContent"]
        assert payload["valid"] is False
        assert "inside the repository" in payload["violations"][0]
        assert payload["file"] == "<repository path>"
        assert secret not in json.dumps(resp)
    finally:
        client.close()


@pytest.mark.parametrize("link_kind", ["file", "directory"])
def test_validate_contract_rejects_symlink_traversal(mcp_root, tmp_path, link_kind):
    secret = "SYMLINK-TARGET-CONTENT-MUST-NOT-ECHO"
    outside_dir = tmp_path / f"outside-{link_kind}"
    outside_dir.mkdir()
    outside_file = outside_dir / "target.brief.json"
    outside_file.write_text(json.dumps(dict(_VALID_BRIEF, step=secret)), encoding="utf-8")
    if link_kind == "file":
        link = mcp_root / "linked.brief.json"
        link.symlink_to(outside_file)
        path_arg = "linked.brief.json"
    else:
        link = mcp_root / "linked-dir"
        link.symlink_to(outside_dir, target_is_directory=True)
        path_arg = "linked-dir/target.brief.json"

    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "validate_contract",
            "arguments": {"contract_type": "brief", "path": path_arg},
        })
        payload = resp["result"]["structuredContent"]
        assert payload["valid"] is False
        assert "without symlink traversal" in payload["violations"][0]
        assert secret not in json.dumps(resp)
    finally:
        client.close()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO fixture requires os.mkfifo")
def test_validate_contract_rejects_special_file_without_blocking(mcp_root):
    fifo = mcp_root / "contract.fifo"
    os.mkfifo(fifo)

    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "validate_contract",
            "arguments": {"contract_type": "brief", "path": "contract.fifo"},
        })
        payload = resp["result"]["structuredContent"]
        assert payload["valid"] is False
        assert "regular repository file" in payload["violations"][0]
    finally:
        client.close()


def test_validate_contract_missing_file_is_infra_error_not_schema_miss(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "validate_contract",
            "arguments": {"contract_type": "brief", "path": "missions/does/not/exist.brief.json"},
        })
        payload = resp["result"]["structuredContent"]
        assert payload["valid"] is False
        assert payload["classification"]["signal"] == "validation_infra_error"
        assert payload["classification"]["failure_state"] == "empty"  # missing file -> "empty", not schema-miss "degraded"
        assert payload["classification"]["cause_class"] == "transient"
    finally:
        client.close()


def test_validate_contract_rejects_path_and_content_together(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "validate_contract",
            "arguments": {"contract_type": "brief", "path": "x.json", "content": "{}", "format": "json"},
        })
        assert resp["error"]["code"] == -32602
        assert "not both" in resp["error"]["message"]
    finally:
        client.close()


# ---------------------------------------------------------------------------
# 4) mission_status
# ---------------------------------------------------------------------------

def test_mission_status_found(mroot):
    r = _mission_run(mroot, "mission", "new", "MCP Status Test Mission")
    assert r.returncode == 0, r.stdout + r.stderr
    mission_id = next(p.name for p in (mroot / "missions").iterdir() if p.is_dir())

    client = McpStdio(mroot)
    try:
        _initialize(client)
        resp = client.request("tools/call", {"name": "mission_status", "arguments": {"mission_id": mission_id}})
        payload = resp["result"]["structuredContent"]
        assert payload["found"] is True
        assert payload["mission_id"] == mission_id
        assert payload["gates_cleared"] == 0
        assert payload["gates_total"] == 5
        assert payload["record"]["name"] == "MCP Status Test Mission"

        # Cross-check against the CLI's own --json output — same underlying read.
        cli = _mission_run(mroot, "mission", "status", mission_id, "--json")
        assert json.loads(cli.stdout) == payload["record"]
    finally:
        client.close()


def test_mission_status_not_found(mroot):
    client = McpStdio(mroot)
    try:
        _initialize(client)
        resp = client.request("tools/call", {"name": "mission_status", "arguments": {"mission_id": "nope-does-not-exist"}})
        payload = resp["result"]["structuredContent"]
        assert payload["found"] is False
        assert "error" in payload
    finally:
        client.close()


def test_mission_status_missing_argument(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {"name": "mission_status", "arguments": {}})
        assert resp["error"]["code"] == -32602
    finally:
        client.close()


# ---------------------------------------------------------------------------
# 5) roster_list
# ---------------------------------------------------------------------------

def test_roster_list_matches_lock_state(project):
    project.add(
        ".claude/agents/ada.md", "ada dispatch\n",
        core_key=".tess/core/agents-dispatch/ada.md", status="core-managed",
    )
    project.add(
        ".claude/agents/iris.md", "iris dispatch\n",
        core_key=".tess/core/agents-dispatch/iris.md", status="core-managed",
    )
    project.add(
        ".claude/agents/vega.md", "vega dispatch\n",
        core_key=".tess/core/agents-dispatch/vega.md", status="staged", render_live=False,
    )
    shutil.copytree(CONTRACTS_SRC, project.root / "core" / "contracts")
    project.write()

    client = McpStdio(project.root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {"name": "roster_list", "arguments": {}})
        payload = resp["result"]["structuredContent"]
        assert payload["installed"] == ["ada", "iris"]
        assert payload["staged"] == ["vega"]
        assert payload["installed_count"] == 2
        assert payload["staged_count"] == 1

        # Cross-check against the CLI's own text report (no --json exists for
        # `roster list`, so assert the human-readable counts line up too).
        cli = subprocess.run(
            [sys.executable, str(project.root / ".tess" / "bin" / "tessctl"), "roster", "list"],
            cwd=str(project.root), env={**os.environ, "TESS_ROOT": str(project.root)},
            capture_output=True, text=True,
        )
        assert "installed (2):" in cli.stdout
        assert "staged / benched (1):" in cli.stdout
    finally:
        client.close()


# ---------------------------------------------------------------------------
# 6) gate_check_paths — diagnostic-only over real stdio pipes. It may expose
#    the shared evaluator's would-block signal, but can never authorize ship.
# ---------------------------------------------------------------------------

def test_gate_check_paths_diagnostic_when_shared_evaluator_would_block(mcp_git_root, run_cli):
    base = _base_sha(mcp_git_root)
    (mcp_git_root / ".tess" / "bin" / "attack.py").write_text("print('tamper')\n")
    head = _commit_all(mcp_git_root, "add protected change, no verdict")

    cli = run_cli(mcp_git_root, "gate", "pre-push", "--base", base, "--head", head, "--json")
    assert cli.returncode == 1, cli.stdout + cli.stderr
    cli_payload = json.loads(cli.stdout)
    assert cli_payload["blocked"] is True

    client = McpStdio(mcp_git_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "gate_check_paths",
            "arguments": {"paths": [".tess/bin/attack.py"], "base": base, "head": head},
        })
        mcp_payload = resp["result"]["structuredContent"]
    finally:
        client.close()

    assert mcp_payload["authoritative"] is False
    assert mcp_payload["blocked"] is True
    assert mcp_payload["diagnostic_would_block"] is True
    assert mcp_payload["changed_paths_count"] == 1
    assert mcp_payload["reasons"] == [
        "MCP_DIAGNOSTIC_ONLY: MCP gate checks cannot authorize shipping",
        "COVERING_APPROVAL_MISSING: no covering APPROVE verdict found",
    ]
    assert ".tess/bin/attack.py" not in json.dumps(mcp_payload)


def test_gate_check_paths_cannot_authorize_when_shared_evaluator_would_allow(mcp_git_root, run_cli):
    base = _base_sha(mcp_git_root)
    (mcp_git_root / "scratch").mkdir()
    (mcp_git_root / "scratch" / "ungated.txt").write_text("diagnostic only\n")
    head = _commit_all(mcp_git_root, "add ungated diagnostic fixture")

    cli = run_cli(mcp_git_root, "gate", "pre-push", "--base", base, "--head", head, "--json")
    assert cli.returncode == 0, cli.stdout + cli.stderr
    cli_payload = json.loads(cli.stdout)
    assert cli_payload["blocked"] is False
    assert cli_payload["reasons"] == []

    client = McpStdio(mcp_git_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "gate_check_paths",
            "arguments": {"paths": ["scratch/ungated.txt"], "base": base, "head": head},
        })
        mcp_payload = resp["result"]["structuredContent"]
    finally:
        client.close()

    assert mcp_payload["authoritative"] is False
    assert mcp_payload["blocked"] is True
    assert mcp_payload["diagnostic_would_block"] is False
    assert mcp_payload["reasons"] == [
        "MCP_DIAGNOSTIC_ONLY: MCP gate checks can never authorize shipping",
    ]
    assert mcp_payload["changed_paths_count"] == 1
    assert "scratch/ungated.txt" not in json.dumps(mcp_payload)


def test_gate_check_paths_defaults_head_to_current_head(mcp_git_root):
    """Omitting `head` resolves HEAD, but still cannot authorize shipping."""
    base = _base_sha(mcp_git_root)
    (mcp_git_root / "scratch").mkdir()
    (mcp_git_root / "scratch" / "notes.md").write_text("nothing special\n")
    real_head = _commit_all(mcp_git_root, "add current-head fixture")

    client = McpStdio(mcp_git_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "gate_check_paths",
            "arguments": {"paths": ["scratch/notes.md"], "base": base},
        })
        payload = resp["result"]["structuredContent"]
        assert payload["authoritative"] is False
        assert payload["blocked"] is True
        assert payload["diagnostic_would_block"] is False
        assert payload["changed_paths_count"] == 1
        assert payload["reasons"] == [
            "MCP_DIAGNOSTIC_ONLY: MCP gate checks cannot authorize shipping",
        ]
        assert real_head not in json.dumps(payload)
        assert base not in json.dumps(payload)
    finally:
        client.close()


def test_gate_check_paths_rejects_caller_path_set_mismatch(mcp_git_root):
    """Reverse direction: an agent cannot omit a governed path and ask the
    MCP surface to authorize a convenient path-only subset."""
    base = _base_sha(mcp_git_root)
    (mcp_git_root / "src" / "prod").mkdir(parents=True)
    (mcp_git_root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    head = _commit_all(mcp_git_root, "governed change")

    client = McpStdio(mcp_git_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "gate_check_paths",
            "arguments": {"paths": ["docs/invented.md"], "base": base, "head": head},
        })
        payload = resp["result"]["structuredContent"]
    finally:
        client.close()

    assert payload["authoritative"] is False
    assert payload["blocked"] is True
    assert "diagnostic_would_block" not in payload
    assert payload["changed_paths_count"] == 1
    assert payload["reasons"] == [
        "MCP_DIAGNOSTIC_ONLY: MCP gate checks cannot authorize shipping",
        "PATH_SET_MISMATCH: the supplied path set does not match the immutable Git diff",
    ]
    assert "src/prod/app.py" not in json.dumps(payload)


@pytest.mark.parametrize("bad_ref_kind", ["same", "tree", "blob", "reversed", "missing"])
def test_gate_check_paths_rejects_invalid_commit_ranges_before_evaluation(mcp_git_root, bad_ref_kind):
    base = _base_sha(mcp_git_root)
    (mcp_git_root / "scratch").mkdir()
    (mcp_git_root / "scratch" / "range.txt").write_text("range fixture\n")
    head = _commit_all(mcp_git_root, "add range fixture")

    if bad_ref_kind == "same":
        bad_base, bad_head = base, base
    elif bad_ref_kind == "tree":
        tree = subprocess.run(
            ["git", "-C", str(mcp_git_root), "rev-parse", f"{base}^{{tree}}"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        bad_base, bad_head = tree, head
    elif bad_ref_kind == "blob":
        blob = subprocess.run(
            ["git", "-C", str(mcp_git_root), "rev-parse", f"{head}:scratch/range.txt"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        bad_base, bad_head = base, blob
    elif bad_ref_kind == "reversed":
        bad_base, bad_head = head, base
    else:
        bad_base, bad_head = "f" * len(base), head

    client = McpStdio(mcp_git_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "gate_check_paths",
            "arguments": {
                "paths": ["scratch/range.txt"],
                "base": bad_base,
                "head": bad_head,
            },
        })
        payload = resp["result"]["structuredContent"]
    finally:
        client.close()

    assert payload["authoritative"] is False
    assert payload["blocked"] is True
    assert "diagnostic_would_block" not in payload
    assert payload["changed_paths_count"] == 0
    assert payload["reasons"][0] == "MCP_DIAGNOSTIC_ONLY: MCP gate checks cannot authorize shipping"
    assert payload["reasons"][1].split(":", 1)[0] in {
        "COMMIT_RANGE_INVALID", "BASE_REQUIRED", "HEAD_REQUIRED",
    }

def test_gate_check_paths_missing_paths_argument(mcp_root):
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {"name": "gate_check_paths", "arguments": {}})
        assert resp["error"]["code"] == -32602
    finally:
        client.close()


def test_gate_check_paths_without_immutable_base_is_explicitly_denied(mcp_root):
    """Reverse direction: MCP cannot silently fall back to candidate trust."""
    client = McpStdio(mcp_root)
    try:
        _initialize(client)
        resp = client.request("tools/call", {
            "name": "gate_check_paths",
            "arguments": {"paths": ["docs/notes.md"]},
        })
        payload = resp["result"]["structuredContent"]
        assert payload["authoritative"] is False
        assert payload["blocked"] is True
        assert payload["changed_paths_count"] == 0
        assert payload["reasons"] == [
            "MCP_DIAGNOSTIC_ONLY: MCP gate checks cannot authorize shipping",
            "BASE_REQUIRED: an immutable BASE commit is required",
        ]
    finally:
        client.close()


def test_gate_check_paths_no_base_denial_never_enters_git_or_gate(engine, tmp_path, monkeypatch):
    """No BASE means no candidate fallback, even before a HEAD is resolved."""
    def forbidden(*_args, **_kwargs):
        raise AssertionError("BASE_REQUIRED must be returned before candidate evaluation")

    monkeypatch.setattr(engine, "_gate_run_git", forbidden)
    monkeypatch.setattr(engine, "_gate_run_ship_check", forbidden)

    result = engine._mcp_tool_gate_check_paths(
        tmp_path, {"paths": ["core/policy/policy.yaml"], "base": "main"},
    )
    assert result["authoritative"] is False
    assert result["blocked"] is True
    assert result["changed_paths_count"] == 0
    assert result["reasons"] == [
        "MCP_DIAGNOSTIC_ONLY: MCP gate checks cannot authorize shipping",
        "BASE_REQUIRED: an immutable BASE commit is required",
    ]


def test_gate_decision_redacts_attacker_sentinel_across_cli_trace_otlp_and_mcp(
    gate_repo, run_cli,
):
    """One governed attacker-controlled pathname must not cross any decision
    output boundary.  The gate still blocks; only its safe code is exported."""
    sentinel = "P73_GATE_SENTINEL_never_export"
    base = _base_sha(gate_repo)
    path = f"src/prod/{sentinel}.py"
    (gate_repo / "src" / "prod").mkdir(parents=True)
    (gate_repo / path).write_text("print('blocked')\n", encoding="utf-8")
    head = _commit_all(gate_repo, "add governed sentinel path")

    cli_json = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head, "--json")
    cli_text = run_cli(gate_repo, "gate", "ci", "--base", base, "--head", head)
    assert cli_json.returncode == cli_text.returncode == 1
    assert sentinel not in (cli_json.stdout + cli_json.stderr + cli_text.stdout + cli_text.stderr)
    payload = json.loads(cli_json.stdout)
    assert payload["reasons"] == ["COVERING_APPROVAL_MISSING: no covering APPROVE verdict found"]

    trace_bytes = b"".join(
        p.read_bytes() for p in (gate_repo / ".tess" / "trace" / "runs").glob("*.jsonl")
    )
    assert sentinel.encode() not in trace_bytes
    otlp = run_cli(gate_repo, "trace", "export", "--format", "otlp-json")
    assert otlp.returncode == 0
    assert sentinel not in (otlp.stdout + otlp.stderr)

    client = McpStdio(gate_repo)
    try:
        _initialize(client)
        response = client.request("tools/call", {
            "name": "gate_check_paths",
            "arguments": {"paths": [path], "base": base, "head": head},
        })
        serialized = json.dumps(response)
        assert sentinel not in serialized
        assert response["result"]["structuredContent"]["blocked"] is True
    finally:
        client.close()


# ---------------------------------------------------------------------------
# 7) The documented Claude Code `.mcp.json` entry — smoke test
# ---------------------------------------------------------------------------

def test_claude_code_mcp_json_entry_smoke_test(wrapper_root):
    """Spawns the server exactly the way docs/MCP.md's Claude Code
    `.mcp.json` snippet does: `command` = the project's `./tessctl`
    wrapper, `args` = ["mcp", "serve"], cwd = project root.
    `${CLAUDE_PROJECT_DIR:-.}` is Claude Code's own env-var expansion
    (out of scope here) — this test pre-resolves it to the fixture root,
    which is exactly what that expansion would produce in real use."""
    client = McpStdio(wrapper_root, use_wrapper=True)
    try:
        init_resp = _initialize(client)
        assert init_resp["result"]["serverInfo"]["name"] == "tessctl"
        list_resp = client.request("tools/list")
        names = {t["name"] for t in list_resp["result"]["tools"]}
        assert names == {"validate_contract", "gate_check_paths", "mission_status", "roster_list"}
        call_resp = client.request("tools/call", {"name": "roster_list", "arguments": {}})
        assert call_resp["result"]["isError"] is False
    finally:
        client.close()


# ---------------------------------------------------------------------------
# 8) `tessctl mcp` at the CLI level
# ---------------------------------------------------------------------------

def test_mcp_serve_exits_cleanly_on_immediate_stdin_eof(mcp_root, run_cli):
    r = run_cli(mcp_root, "mcp", "serve", input_text="")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout == ""


def test_mcp_no_subcommand_refuses(mcp_root, run_cli):
    r = run_cli(mcp_root, "mcp")
    assert r.returncode != 0
    assert "choose a subcommand" in (r.stdout + r.stderr)


def test_mcp_tools_list_matches_engine_registry_exactly(engine):
    """Direct, in-process sanity check: the tools/list result is derived
    from MCP_TOOLS, not a hand-maintained parallel list that could drift."""
    result = engine._mcp_tools_list_result()
    names = [t["name"] for t in result["tools"]]
    assert names == sorted(engine.MCP_TOOLS.keys())
    assert set(names) == {"validate_contract", "gate_check_paths", "mission_status", "roster_list"}
