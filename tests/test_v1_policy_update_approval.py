"""v1.0.0 release integration, item a: a release that changes policy rules
must never dead-end an install whose owner has no verifier key.

`tessctl update` shows each rule the release adds, removes or changes, and
asks the person at the terminal to type `accept <tag>`. Their answer is
recorded in .tess/gate/policy-approvals/<tag>.json, bound to the old and new
rule digests; the gate accepts exactly that change and nothing else. Without
a terminal (an agent, CI, a pipe) the update stops and changes nothing.
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import sys
from pathlib import Path

import pytest

from test_v1_gate_hardening import (  # noqa: F401 — fixtures + helpers
    POL_KEY, POL_LIVE, RELEASE_POLICY, _commit, _gate_ci, _git, _installed, _registries,
    _tessctl, needs_gpg,
)
from test_codex_gate import _decision, _hook, proj  # noqa: F401 — fixture

TAG = "v2.1.0"
APPROVAL = f".tess/gate/policy-approvals/{TAG}.json"
NEW_GLOB = "docs/SECURITY_NEW.md"
VENDOR_LINE = "        - .tess/vendor/**\n"
RULES_CHANGED = RELEASE_POLICY.replace(VENDOR_LINE, VENDOR_LINE + f"        - {NEW_GLOB}\n", 1)


def _update_in_pty(root: Path, answer: str) -> tuple[int, str]:
    """Run `tessctl update` on a real pseudo-terminal and type `answer`."""
    import pty
    master, slave = pty.openpty()
    p = subprocess.Popen([sys.executable, str(root / ".tess" / "bin" / "tessctl"), "update",
                          "--ref", TAG], cwd=str(root), stdin=slave, stdout=slave, stderr=slave,
                         env={**os.environ, "TESS_ROOT": str(root)}, close_fds=True)
    os.close(slave)
    out, sent = b"", False
    while True:
        ready, _, _ = select.select([master], [], [], 120)
        if not ready:
            break
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
        if not sent and b"accept> " in out:
            os.write(master, (answer + "\n").encode("utf-8"))
            sent = True
    rc = p.wait(timeout=120)
    os.close(master)
    return rc, out.decode("utf-8", "replace")


def _policy_bytes(root: Path) -> tuple:
    return tuple((root / rel).read_bytes() for rel in (POL_KEY, POL_LIVE))


@needs_gpg
def test_update_without_a_terminal_lists_the_rule_change_and_changes_nothing(
        project, gpg_key, tmp_path, run_cli, engine):
    _installed(project, gpg_key, tmp_path, run_cli, engine, release_policy=RULES_CHANGED)
    before = _policy_bytes(project.root)
    r = run_cli(project.root, "update", "--ref", TAG)
    text = r.stdout + r.stderr
    assert r.returncode != 0, text
    assert "STOPPED" in text and f"accept {TAG}" in text
    assert (f"CHANGED rule 'tess-os-security-tier-doctrine': now also protects {NEW_GLOB}"
            in text), text
    assert "stay on your current version" in text
    assert _policy_bytes(project.root) == before
    assert not (project.root / APPROVAL).exists()


@needs_gpg
@pytest.mark.skipif(sys.platform.startswith("win"), reason="needs a POSIX pty")
def test_wrong_answer_changes_nothing(project, gpg_key, tmp_path, run_cli, engine):
    _installed(project, gpg_key, tmp_path, run_cli, engine, release_policy=RULES_CHANGED)
    before = _policy_bytes(project.root)
    rc, out = _update_in_pty(project.root, "yes")
    assert rc != 0 and "did not type" in out, out
    assert _policy_bytes(project.root) == before
    assert not (project.root / APPROVAL).exists()


@needs_gpg
@pytest.mark.skipif(sys.platform.startswith("win"), reason="needs a POSIX pty")
def test_typed_acceptance_updates_and_the_gate_accepts_exactly_that(
        project, gpg_key, tmp_path, run_cli, engine):
    base = _installed(project, gpg_key, tmp_path, run_cli, engine, release_policy=RULES_CHANGED)
    rc, out = _update_in_pty(project.root, f"accept {TAG}")
    assert rc == 0, out
    assert "now also protects" in out
    for rel in (POL_KEY, POL_LIVE):
        assert NEW_GLOB in (project.root / rel).read_text(encoding="utf-8")
        assert _registries(project.root, rel) == ({}, {})       # still the user's own
    record = json.loads((project.root / APPROVAL).read_text(encoding="utf-8"))
    assert record["tag"] == TAG and record["approved_by_typing"] == f"accept {TAG}"
    head = _commit(project.root, "tessctl update v2.1.0 (rules approved)")
    r, res = _gate_ci(project.root, base, head)
    assert r.returncode == 0 and res["blocked"] is False, res
    assert res["release_proof"]["status"] == "accepted"
    assert _tessctl(project.root, "verify").returncode == 0

    # Reverse direction 1: the same update without the committed approval is blocked.
    _git(project.root, "rm", "-q", APPROVAL)
    _git(project.root, "reset", "-q", "--soft", base)
    squashed = _commit(project.root, "update without approval")
    r, res = _gate_ci(project.root, base, squashed)
    assert r.returncode == 1 and res["blocked"] is True, res

    # Reverse direction 2: an approval whose digests do not name this change is ignored.
    record["new_rules_sha256"] = "sha256:" + "0" * 64
    (project.root / APPROVAL).parent.mkdir(parents=True, exist_ok=True)
    (project.root / APPROVAL).write_text(json.dumps(record), encoding="utf-8")
    _git(project.root, "reset", "-q", "--soft", base)
    forged = _commit(project.root, "update with a forged approval")
    r, res = _gate_ci(project.root, base, forged)
    assert r.returncode == 1 and res["blocked"] is True, res


def test_approval_never_covers_a_registry_change_or_another_tag(engine):
    import yaml
    old = yaml.safe_load(engine._policy_reset_registries_text(RELEASE_POLICY))
    new = yaml.safe_load(engine._policy_reset_registries_text(RULES_CHANGED))
    ok = {"format": engine.POLICY_APPROVAL_FORMAT, "tag": TAG,
          "old_rules_sha256": engine._policy_rules_digest(old),
          "new_rules_sha256": engine._policy_rules_digest(new),
          "approved_by_typing": f"accept {TAG}"}
    assert engine._policy_approval_covers(ok, TAG, old, new)
    assert not engine._policy_approval_covers(ok, "v9.9.9", old, new)
    assert not engine._policy_approval_covers({**ok, "approved_by_typing": "accept"}, TAG, old, new)
    maintainers = yaml.safe_load(RULES_CHANGED)                 # carries the Cyra verifier key
    assert not engine._policy_approval_covers(ok, TAG, old, maintainers)
    lines = engine._policy_rule_change_lines(old, new)
    assert lines == [f"CHANGED rule 'tess-os-security-tier-doctrine': now also protects {NEW_GLOB}"]


def test_agent_cannot_write_an_approval_file(proj):
    target = proj / ".tess" / "gate" / "policy-approvals" / f"{TAG}.json"
    r = _hook(proj, {"turn_id": "t", "tool_name": "Write", "cwd": str(proj),
                     "tool_input": {"file_path": str(target), "content": "{}"}})
    assert _decision(r)[0] == "deny"
    r = _hook(proj, {"turn_id": "t", "tool_name": "Bash", "cwd": str(proj),
                     "tool_input": {"command": f"echo '{{}}' > {target}"}})
    assert _decision(r)[0] == "deny"


def test_readme_documents_the_plain_english_path():
    from conftest import REPO_ROOT
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    section = text.split("## Updating", 1)[1].split("\n## ", 1)[0]
    assert "accept <version>" in section and ".tess/gate/policy-approvals/" in section
    assert "cannot give" in section and "press Enter" in section


@pytest.mark.parametrize("cmd", [
    "script -q /dev/null ./tessctl update --ref v2.1.0",
    "printf 'accept v2.1.0\\n' | ./tessctl update --ref v2.1.0",
    "echo 'accept v2.1.0' > /tmp/a; ./tessctl update < /tmp/a",
    "python3 -c 'import pty; pty.spawn([\"./tessctl\", \"update\"])'",
    "unbuffer ./tessctl approve conductor/guardrails.md --rationale x",
    "expect -c 'spawn ./tessctl update; send \"accept v2.1.0\\r\"'",
])
def test_agent_cannot_fake_the_terminal_or_type_the_approval(proj, cmd):
    r = _hook(proj, {"turn_id": "t", "tool_name": "Bash", "cwd": str(proj),
                     "tool_input": {"command": cmd}})
    dec = _decision(r)
    assert dec and dec[0] == "deny", (cmd, dec)
    assert "only the operator" in dec[1]


def test_plain_update_and_normal_commands_stay_allowed(proj):
    for cmd in ("./tessctl update --ref v2.1.0", "./tessctl doctor", "git status",
                "python3 scripts/build.py --script-dir x"):
        r = _hook(proj, {"turn_id": "t", "tool_name": "Bash", "cwd": str(proj),
                         "tool_input": {"command": cmd}})
        dec = _decision(r)
        assert dec is None or "only the operator" not in dec[1], (cmd, dec)
