"""v1.0.0 release integration, item a: a release that changes policy rules
must never dead-end an install whose owner has no verifier key.

`tessctl update` shows each rule the release adds, removes or changes, and
asks the person at the terminal to type `accept <tag>`. Their answer is
recorded in .tess/gate/policy-approvals/<tag>.json, bound to the old and new
rule digests; the gate accepts exactly that change and nothing else. Without
a terminal (an agent, CI, a pipe) the update stops and changes nothing.

v1.0.1 (GPT-6 review round 2, HIGH): the approval is signed. It carries an
HMAC under a per-machine operator key kept outside the repo
($XDG_CONFIG_HOME/tess/operator/key), bound to the project's root commit, the
release tag and commit, and the rule digests. Unsigned, hand-written, foreign
or keyless approvals are rejected, and the approvals directory is protected.
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


FAKE_OS_HOME_SITE = Path(__file__).resolve().parent / "fixtures" / "fake_os_home"


def _use_os_home(monkeypatch, home: Path) -> None:
    """Point the OS user record's home at `home` for this process and for every
    tessctl subprocess (tests/fixtures/fake_os_home/sitecustomize.py). Round 3
    (N-2): tessctl ignores $HOME / $XDG_CONFIG_HOME for the operator key, so an
    environment variable no longer moves it."""
    import pwd
    monkeypatch.setenv("TESS_TEST_OS_HOME", str(home))
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(
        [str(FAKE_OS_HOME_SITE)] + [p for p in [os.environ.get("PYTHONPATH")] if p]))
    real = pwd.getpwuid

    def fake(uid):
        rec = real(uid)
        return pwd.struct_passwd((rec.pw_name, rec.pw_passwd, rec.pw_uid, rec.pw_gid,
                                  rec.pw_gecos, os.environ["TESS_TEST_OS_HOME"], rec.pw_shell))
    monkeypatch.setattr(pwd, "getpwuid", fake)


@pytest.fixture(autouse=True)
def _operator_home(tmp_path_factory, monkeypatch):
    """Every test gets its own operator key location, never the real ~/.config."""
    home = tmp_path_factory.mktemp("os-home")  # outside every test project
    _use_os_home(monkeypatch, home)
    return home / ".config"


def _write_approval(root: Path, record: dict) -> None:
    (root / APPROVAL).parent.mkdir(parents=True, exist_ok=True)
    (root / APPROVAL).write_text(json.dumps(record), encoding="utf-8")


def _recommit_update(root: Path, base: str, msg: str) -> str:
    _git(root, "reset", "-q", "--soft", base)
    return _commit(root, msg)


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
    assert record["format"] == engine.POLICY_APPROVAL_FORMAT
    assert record["mac"].startswith("hmac-sha256:") and record["release_commit"]
    assert record["project_id"] == engine._project_identity(project.root, base)
    key_file = Path(os.environ["TESS_TEST_OS_HOME"]) / ".config" / "tess" / "operator" / "key"
    assert key_file.is_file() and (key_file.stat().st_mode & 0o777) == 0o600
    assert not str(key_file.resolve()).startswith(str(project.root.resolve()))
    genuine = dict(record)
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

    # Reverse direction 3 (round 2): hand-written JSON with the RIGHT digests
    # but no operator signature (what a repo-only writer can produce).
    unsigned = {k: v for k, v in genuine.items() if k != "mac"}
    for forged_record in (unsigned, {**unsigned, "format": "tess-policy-approval/1"},
                          {**genuine, "mac": "hmac-sha256:" + "0" * 64}):
        _write_approval(project.root, forged_record)
        r, res = _gate_ci(project.root, base, _recommit_update(project.root, base, "forged"))
        assert r.returncode == 1 and res["blocked"] is True, (forged_record, res)
        assert res["release_proof"]["policy_approval"] == "rejected", res

    # Reverse direction 4: a genuinely signed approval, but for ANOTHER project
    # (same machine, same key, different root commit).
    key = key_file.read_bytes()
    other = {**genuine, "project_id": "git-root:" + "1" * 40}
    other["mac"] = engine._policy_approval_mac(
        key, other["project_id"], TAG, other["release_commit"], other["old_rules_sha256"],
        other["new_rules_sha256"], other["approved_at"])
    _write_approval(project.root, other)
    r, res = _gate_ci(project.root, base, _recommit_update(project.root, base, "foreign"))
    assert r.returncode == 1 and res["blocked"] is True, res

    # Reverse direction 5: the genuine approval, checked where the operator key
    # is absent (a CI runner, another machine): cannot be verified, so blocked.
    _write_approval(project.root, genuine)
    again = _recommit_update(project.root, base, "genuine again")
    r, res = _gate_ci(project.root, base, again)
    assert r.returncode == 0 and res["blocked"] is False, res
    os.environ["TESS_TEST_OS_HOME"] = str(Path(os.environ["TESS_TEST_OS_HOME"]).parent / "no-key-here")
    r, res = _gate_ci(project.root, base, again)
    assert r.returncode == 1 and res["blocked"] is True, res


def test_signed_approval_checks_project_release_and_key(engine):
    key, other_key = b"k" * 32, b"o" * 32
    args = ("git-root:" + "a" * 40, TAG, "c" * 40, "sha256:old", "sha256:new",
            "2026-09-29T00:00:00Z")
    rec = {"format": engine.POLICY_APPROVAL_FORMAT, "project_id": args[0], "tag": TAG,
           "release_commit": args[2], "old_rules_sha256": args[3], "new_rules_sha256": args[4],
           "approved_at": args[5], "mac": engine._policy_approval_mac(key, *args)}
    ok = engine._policy_approval_authentic
    assert ok(rec, key, args[0], TAG, args[2]) is None
    assert "different project" in ok(rec, key, "git-root:" + "b" * 40, TAG, args[2])
    assert "release commit" in ok(rec, key, args[0], TAG, "d" * 40)
    assert "does not verify" in ok(rec, other_key, args[0], TAG, args[2])
    assert "no operator key" in ok(rec, None, args[0], TAG, args[2])
    unsigned = {k: v for k, v in rec.items() if k != "mac"}
    assert "not signed" in ok(unsigned, key, args[0], TAG, args[2])
    later = {**rec, "approved_at": "2027-01-01T00:00:00Z"}
    assert "does not verify" in ok(later, key, args[0], TAG, args[2])


def test_operator_key_lives_outside_the_project_and_is_private(engine, tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    _use_os_home(monkeypatch, proj)
    key, why = engine._operator_key(proj, create=True)
    assert key is None and "inside this project" in why
    assert not (proj / ".config").exists()
    _use_os_home(monkeypatch, tmp_path / "cfg")
    assert engine._operator_key(proj, create=False) == (None, "there is no operator key on this machine")
    key, why = engine._operator_key(proj, create=True)
    assert key is not None and len(key) == 32 and why == ""
    assert engine._operator_key(proj, create=True)[0] == key       # stable, not re-created
    if os.name == "posix":
        (tmp_path / "cfg" / ".config" / "tess" / "operator" / "key").chmod(0o644)
        key, why = engine._operator_key(proj, create=False)
        assert key is None and "accessible to other users" in why


def test_approvals_directory_is_itself_protected(engine):
    import yaml
    from conftest import REPO_ROOT
    for rel in ("core/policy/policy.yaml", ".tess/core/policy/policy.yaml"):
        policy = yaml.safe_load((REPO_ROOT / rel).read_text(encoding="utf-8"))
        matches, _ = engine._gate_classify_paths(policy, [APPROVAL])
        assert APPROVAL in matches, rel


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


def test_operator_key_ignores_home_and_xdg_config_home(engine, tmp_path, monkeypatch):
    """Round 3, N-2: `XDG_CONFIG_HOME=/tmp/x tessctl ...` (or a moved HOME) must
    not make tessctl read a key the agent planted. The key directory comes from
    the OS user record; the planted key is never read and nothing is created there."""
    proj, planted = tmp_path / "proj", tmp_path / "agent-cfg"
    proj.mkdir()
    (planted / "tess" / "operator").mkdir(parents=True, mode=0o700)
    (planted / "tess" / "operator" / "key").write_bytes(b"p" * 32)
    (planted / "tess" / "operator" / "key").chmod(0o600)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(planted))
    monkeypatch.setenv("HOME", str(planted))
    real_home = Path(os.environ["TESS_TEST_OS_HOME"])
    assert engine._operator_key_dir() == real_home / ".config" / "tess" / "operator"
    assert engine._operator_key(proj, create=False) == (None, "there is no operator key on this machine")
    key, why = engine._operator_key(proj, create=True)
    assert key is not None and key != b"p" * 32 and why == ""
    assert (real_home / ".config" / "tess" / "operator" / "key").read_bytes() == key
    assert (planted / "tess" / "operator" / "key").read_bytes() == b"p" * 32


def test_tessctl_subprocess_ignores_xdg_config_home(engine, tmp_path, monkeypatch):
    """The same through a real tessctl process (the pre-push gate path)."""
    planted = tmp_path / "agent-cfg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(planted))
    code = ("import importlib.machinery, importlib.util, sys; "
            "l = importlib.machinery.SourceFileLoader('t', sys.argv[1]); "
            "s = importlib.util.spec_from_loader('t', l); m = importlib.util.module_from_spec(s); "
            "l.exec_module(m); print(m._operator_key_dir())")
    from conftest import REPO_ROOT
    r = subprocess.run([sys.executable, "-c", code, str(REPO_ROOT / ".tess" / "bin" / "tessctl")],
                       capture_output=True, text=True, env=dict(os.environ))
    assert r.returncode == 0, r.stderr
    out = Path(r.stdout.strip())
    assert out == Path(os.environ["TESS_TEST_OS_HOME"]) / ".config" / "tess" / "operator"
    assert str(planted) not in r.stdout
