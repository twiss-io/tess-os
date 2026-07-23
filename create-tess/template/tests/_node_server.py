"""Shared "boot a generated Node app for real" helper.

Extracted from `tests/spec_engine/test_codegen_app_boots.py` (the ONLY
place this fixture originally lived) so a second consumer —
`tests/orchestrator/test_e2e_wedge_loop.py`'s DoD B.9 "propose -> approve
-> app boots -> show me the receipt" e2e — can spawn and talk to the SAME
real `node` child process without copy-pasting the boot-polling logic (or,
worse, silently drifting a second implementation of it). Nothing about
the boot mechanism changed in this extraction — this is a pure move.

Deliberately named `_node_server.py`, not `conftest.py`: neither
`tests/orchestrator/` nor `tests/spec_engine/` (nor `tests/` itself) carries
an `__init__.py`, so pytest's default "prepend" import mode loads every
helper file under its bare module name regardless of directory — see
`tests/orchestrator/_orchestrator_paths.py`'s own docstring for the
collision this discipline avoids. `pytest.ini`'s `pythonpath = tests`
setting is what makes `import _node_server` resolve from ANY test file
under `tests/` (this file's own directory, `tests/`, is already on
`sys.path` for every test run) — the same mechanism `tests/
_agent_receipt_fixtures.py` and `tests/_receipt_emit_fixtures.py` already
rely on for their own cross-directory reuse.

Requires a real `node` binary on PATH (Node >=18, for `node:test` +
built-in `fetch()` — see `spec_engine.codegen`'s module docstring for why
this target stack was chosen). `HAS_NODE` is exported so each CONSUMER
decides for itself how to react to a missing `node` — `test_codegen_app_
boots.py` skips cleanly (a local-dev convenience); `test_e2e_wedge_loop.py`
deliberately does NOT skip (a flagship "show me the receipt" proof must
actually run in CI, never silently vanish) — see that module's own
docstring.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from shutil import which

import pytest

HAS_NODE = which("node") is not None

BOOT_TIMEOUT_SECONDS = 10
_LISTEN_RE = re.compile(r"listening on http://localhost:(\d+)")
_NODE_TEST_PASS_RE = re.compile(r"(?m)^[#ℹ] pass (?P<count>[1-9]\d*)\s*$")
_NODE_TEST_FAIL_RE = re.compile(r"(?m)^[#ℹ] fail (?P<count>\d+)\s*$")


def assert_node_test_passed(result: subprocess.CompletedProcess, *, description: str) -> None:
    """Require a generated app's real ``node --test`` run to have passed.

    Node 18--22 use the TAP reporter for a captured stream (``# pass`` /
    ``# fail``); newer Node releases use the spec reporter (``ℹ pass`` /
    ``ℹ fail``). The runner's exit code is the primary success signal, but
    the summary check remains deliberate: it proves this explicit generated
    test file actually ran at least one test rather than merely exiting zero.
    """
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise AssertionError(f"{description} exited with code {result.returncode}:\n{output}")

    passed = _NODE_TEST_PASS_RE.search(output)
    failed = _NODE_TEST_FAIL_RE.search(output)
    if passed is None or failed is None:
        raise AssertionError(
            f"{description} did not emit a recognized Node test summary:\n{output}"
        )
    if int(failed.group("count")) != 0:
        raise AssertionError(f"{description} reported {failed.group('count')} failed test(s):\n{output}")


@pytest.fixture
def node_server():
    """Yields a `start(target_dir, extra_env=None) -> (proc, base_url)`
    helper; always terminates the spawned process (and drains its pipes)
    on teardown, even if the test body raises."""
    procs = []

    def start(target_dir, extra_env=None):
        env = {**os.environ, "PORT": "0"}
        if extra_env:
            env.update(extra_env)
        proc = subprocess.Popen(
            ["node", str(target_dir / "src" / "server.js")],
            cwd=str(target_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        procs.append(proc)
        deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
        port = None
        stdout_so_far = ""
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stderr_out = proc.stderr.read()
                raise AssertionError(
                    f"generated server exited early (code {proc.returncode}) before reporting "
                    f"'listening'. stdout={stdout_so_far!r} stderr={stderr_out!r}"
                )
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            stdout_so_far += line
            match = _LISTEN_RE.search(line)
            if match:
                port = int(match.group(1))
                break
        if port is None:
            proc.terminate()
            raise AssertionError(
                f"generated server did not report 'listening' within {BOOT_TIMEOUT_SECONDS}s. "
                f"stdout so far: {stdout_so_far!r}"
            )
        return proc, f"http://localhost:{port}"

    yield start

    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def get_json(url, timeout=5):
    """GET `url`, returning `(status, parsed_json_body)` for both the
    success and HTTPError paths (the generated app's own error responses
    are JSON too — see `spec_engine.codegen`'s server template)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def post_json(url, payload, timeout=5):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


__all__ = ["HAS_NODE", "BOOT_TIMEOUT_SECONDS", "node_server", "get_json", "post_json"]
