"""Proves telemetry/ never opens a socket -- mirrors docs/OBSERVABILITY.md's
own tessctl-trace precedent (tests/test_trace_otel.py) for this repo's
OTHER local-first JSONL instrumentation system, applied here to
telemetry/'s v1 "no phone-home" guarantee (docs/TELEMETRY.md)."""

from __future__ import annotations

import ast

import _telemetry_paths  # noqa: F401 -- sys.path bootstrap
from _telemetry_paths import REPO_ROOT

from telemetry import consent, store, summary
from telemetry.events import record_mission_completion

_TELEMETRY_DIR = REPO_ROOT / "telemetry"
_FORBIDDEN_MODULES = {"socket", "http.client", "urllib.request", "requests", "httpx", "aiohttp"}


def test_no_source_file_imports_a_networking_library():
    for path in sorted(_TELEMETRY_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = {node.module}
            else:
                continue
            offending = names & _FORBIDDEN_MODULES
            assert not offending, f"{path} imports forbidden networking module(s): {offending}"


def test_full_call_graph_completes_with_socket_creation_blocked(monkeypatch, tmp_path):
    """Monkeypatch socket.socket/create_connection/getaddrinfo to raise,
    then run consent.enable() -> record_mission_completion() (twice) ->
    summary.build_summary() -> store.delete_all() -- the entire call
    graph this component exposes -- and assert it all still completes
    normally. If anything here ever reached for a socket, this test
    fails with a clear traceback instead of silently passing."""
    import socket as socket_module

    def _raise(*args, **kwargs):
        raise AssertionError("telemetry/ attempted to open a network socket")

    monkeypatch.setattr(socket_module, "socket", _raise)
    monkeypatch.setattr(socket_module, "create_connection", _raise)
    monkeypatch.setattr(socket_module, "getaddrinfo", _raise)

    telemetry_dir = tmp_path / "telemetry"
    consent.enable(telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    record_mission_completion(telemetry_dir=telemetry_dir)
    result = summary.build_summary(store.default_events_log_path(telemetry_dir))
    assert result.total_missions == 2
    store.delete_all(telemetry_dir)
