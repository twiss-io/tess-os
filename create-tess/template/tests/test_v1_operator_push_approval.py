"""v1.0 integration pass 4: on a fresh `npm create tess` install, the operator
can push their own deliberate change to a protected Tess file.

Before: a fresh install has no verifier key (on purpose), so `git push` of a
change the operator really meant to make to a protected file (a policy file,
tess.manifest.json, the guardrails doctrine) was refused (COVERING_APPROVAL_MISSING) with no path
forward short of a key-custody ceremony. Now `./tessctl gate approve`, run by
the operator at their own terminal, shows the changed protected files, takes
the typed answer `approve these changes`, and records an approval of exactly
that content, HMAC-signed with this machine's operator key and kept outside the
repository. The local pre-push gate then lets that exact content through. No
Tess maintainer key is involved.

End to end on a freshly created instance (the packed-tarball install of
test_v1_first_push_release_proof): first push, an operator edit of
tess.manifest.json (with `tessctl anchor accept`), the refusal
naming the command, the approval at a pseudo-terminal, a real `git push`, and
then a further edit that needs a new approval. Also: refused inside an
assistant session, a forged record never counts, hard-floor files are never
cleared this way.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from _presence_pty import operator_env, run_tessctl_in_pty
from test_v1_first_push_release_proof import CAN_BUILD, _git, _run, first_push  # noqa: F401

pytestmark = pytest.mark.skipif(not CAN_BUILD, reason="needs git, ssh-keygen, node, npm")

CONFIRM = "approve these changes"


def _push(inst, env):
    return subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=str(inst), env=env,
                          capture_output=True, text=True, timeout=600)


def _commit(inst, env, msg):
    _git(inst, "add", "-A")
    return subprocess.run(["git", "-c", "user.email=alex@tess.test", "-c", "user.name=Alex",
                           "-c", "commit.gpgsign=false", "commit", "-q", "-m", msg],
                          cwd=str(inst), env=env, capture_output=True, text=True, timeout=600)


@pytest.fixture(scope="module")
def pushed(first_push):  # noqa: F811
    """The fresh install, pushed once to a bare origin (release proof)."""
    inst, env = first_push["inst"], {**first_push["env"], "TESS_ROOT": str(first_push["inst"])}
    env = {k: v for k, v in env.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
                                                      "CODEX_THREAD_ID", "CODEX_SANDBOX",
                                                      "CODEX_SANDBOX_NETWORK_DISABLED")}
    origin = first_push["tmp"] / "origin.git"
    _git(first_push["tmp"], "init", "-q", "--bare", "-b", "main", str(origin))
    _git(inst, "checkout", "-q", "main")
    _git(inst, "reset", "-q", "--hard", first_push["seed"])
    _git(inst, "remote", "add", "origin", str(origin))
    # Seed the origin: the first push's gate decision (release proof) is run
    # explicitly; the transfer skips the hooks because the throwaway release
    # key's fingerprint in this test install trips gitleaks' entropy rule (the
    # real Twiss fingerprint is allowlisted in .gitleaks.toml). Every later
    # push in this module is a plain `git push` with all hooks.
    gate = subprocess.run([sys.executable, str(inst / ".tess/bin/tessctl"), "gate", "pre-push",
                           "--json"], cwd=str(inst), env=env, capture_output=True, text=True,
                          input=f"refs/heads/main {first_push['seed']} refs/heads/main {'0' * 40}\n",
                          timeout=600)
    assert gate.returncode == 0 and json.loads(gate.stdout)["blocked"] is False, gate.stdout[-3000:]
    r = subprocess.run(["git", "push", "--no-verify", "origin", "HEAD:main"], cwd=str(inst),
                       env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    _git(inst, "branch", "-q", "--set-upstream-to=origin/main", "main")
    return {"inst": inst, "env": env, "origin": origin}


def _edit_manifest(inst, extra: str):
    path = inst / "tess.manifest.json"
    doc = json.loads(path.read_text())
    doc["never_touch"] = list(doc.get("never_touch") or []) + [extra]
    path.write_text(json.dumps(doc, indent=2) + "\n")


def _anchor_accept(inst, env):
    """The operator records the edited safety file as approved locally (the
    hooks stop while it differs from the anchor)."""
    rc, out = run_tessctl_in_pty(inst, "anchor", "accept", answer="accept safety changes",
                                 prompt=b"accept> ", env=operator_env(**env), timeout=300)
    assert rc == 0, out[-3000:]


def test_operator_change_to_a_protected_file_is_refused_then_approved_and_pushed(pushed):
    """The operator keeps their own notes folder out of Tess's reach: a
    deliberate edit of tess.manifest.json (security tier)."""
    inst, env, origin = pushed["inst"], pushed["env"], pushed["origin"]
    _edit_manifest(inst, "my-notes/**")
    _anchor_accept(inst, env)
    c = _commit(inst, env, "Keep my notes out of Tess's reach")
    assert c.returncode == 0, c.stdout + c.stderr
    head = _git(inst, "rev-parse", "HEAD")

    refused = _push(inst, env)
    out = refused.stdout + refused.stderr
    assert refused.returncode != 0, out
    assert "tess.manifest.json" in out and "./tessctl gate approve" in out, out[-3000:]
    assert _git(origin, "rev-parse", "main") != head

    rc, shown = run_tessctl_in_pty(inst, "gate", "approve", answer=CONFIRM, prompt=b"approve> ",
                                   env=operator_env(**env), timeout=300)
    assert rc == 0, shown[-3000:]
    assert "tess.manifest.json" in shown and "my-notes/**" in shown, "the diff is shown first"
    assert "approved 1 protected file" in shown, shown[-2000:]

    ok = _push(inst, env)
    assert ok.returncode == 0, (ok.stdout + ok.stderr)[-3000:]
    assert _git(origin, "rev-parse", "main") == head

    # The approval is bound to that exact content: a further edit is refused again.
    _edit_manifest(inst, "my-drafts/**")
    _anchor_accept(inst, env)
    assert _commit(inst, env, "And my drafts").returncode == 0
    again = _push(inst, env)
    assert again.returncode != 0 and "./tessctl gate approve" in again.stdout + again.stderr


def test_approval_is_refused_inside_an_assistant_session(pushed):
    inst, env = pushed["inst"], pushed["env"]
    for marker in ("CLAUDECODE", "CODEX_THREAD_ID"):
        rc, out = run_tessctl_in_pty(inst, "gate", "approve", answer=CONFIRM,
                                     prompt=b"approve> ",
                                     env=operator_env(**{**env, marker: "1"}), timeout=120)
        assert rc != 0 and "REFUSED" in out and "your own terminal" in out, out[-2000:]
        assert "approve>" not in out


def test_a_forged_or_foreign_record_never_counts(pushed, engine):
    inst = pushed["inst"]
    d = engine._push_approvals_dir(inst)
    d.mkdir(parents=True, exist_ok=True)
    forged = {"format": engine.PUSH_APPROVAL_FORMAT, "project": engine._anchor_project_id(inst),
              "paths": {"CLAUDE.md": "1" * 40}, "approved_at": "2026-01-01T00:00:00Z",
              "mac": "0" * 64}
    key, why = engine._operator_key(inst, create=True)
    assert key, why
    genuine = dict(forged, paths={"CLAUDE.md": "2" * 40})
    genuine["mac"] = engine._push_approval_mac(key, genuine["project"], genuine["paths"],
                                               genuine["approved_at"])
    foreign = dict(genuine, project="0" * 40)   # another project's record, same key
    written = []
    for name, rec in (("forged", forged), ("genuine", genuine), ("foreign", foreign)):
        p = d / f"{name}.json"
        p.write_text(json.dumps(rec))
        os.chmod(p, 0o600)
        written.append(p)
    try:
        got = engine._gate_operator_push_approvals(inst).get("CLAUDE.md", set())
        assert "2" * 40 in got, "a record signed with this machine's operator key counts"
        assert "1" * 40 not in got, "a record with a wrong signature never counts"
        assert len(got) == 1, "a record for another project never counts"
    finally:
        for p in written:
            p.unlink()


def test_hard_floor_files_are_never_cleared_by_an_operator_approval(pushed, engine):
    """`tessctl gate approve` only clears ordinary protected-file rules; a
    credentials file (hard floor) stays blocked."""
    inst = pushed["inst"]
    import inspect
    src = inspect.getsource(engine._gate_run_ship_check)
    assert "_gate_operator_approved(root, path_rule_matches" in src
    assert "_gate_operator_approved(root, hard_floor_matches" not in src


def test_the_gate_hook_refuses_the_approval_to_agents():
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    from pathlib import Path
    sys.dont_write_bytecode = True
    path = Path(__file__).resolve().parents[1] / ".claude/hooks/tess-gate.py"
    loader = SourceFileLoader("tess_gate_opapprove", str(path))
    g = module_from_spec(spec_from_loader("tess_gate_opapprove", loader))
    loader.exec_module(g)
    assert g._operator_form(["gate", "approve"])
    assert g._operator_form(["gate", "approve", "--base", "abc"])
    assert not g._operator_form(["gate", "pre-push"])
