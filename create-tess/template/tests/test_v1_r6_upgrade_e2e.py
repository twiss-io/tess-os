"""v1.0.0 round 6 (GPT-6 #1 / #2): the documented 0.2.0 -> 1.0.0 upgrade, end to end.

A real 0.2.0 install (the v0.2.0 tag's create-tess template, set up with the
0.2.0 engine's own wizard verbs, committed and pushed to an origin) upgrades
from a local upstream whose signed `v1.0.0` tag is THIS tree, signed with
throwaway OpenPGP and SSH release keys:

    ./tessctl self-update --ref v1.0.0     (the 0.2.0 engine)
    ./tessctl update --ref v1.0.0          (the new engine, at a terminal)

Then every script `.claude/settings.json` and `.codex/config.toml` (and a
`.codex/hooks.json`, if any) run must be installed with its pinned sha256,
`tessctl verify`, `lock --check`, `scripts/tess hooks-status` and an evaluated
gate call must work, and the first push of the update must pass the review
gate with no verdict (explicit gate run, then a real `git push`). Finally the
new engine's own `self-update --ref v1.0.1` is committed and pushed on its
own, then `update --ref v1.0.1`: both pass the gate on the release proof.
Everything runs under a throwaway OS-record home; nothing touches ~/.config.

At 8f78d69 every test here fails: run-pinned.py, tess-gate.py and the v1
brain were never installed, so the rendered PreToolUse hook could not start
and Claude Code refused every tool call. Runtime is about two minutes (one
0.2.0 install and three signed release runs); there is no slow-test marker
in this suite, so it runs in the normal suite.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from _presence_pty import operator_env, run_tessctl_in_pty
from conftest import HAS_GIT, HAS_GPG, REPO_ROOT
from fixtures.os_home import use_os_home
from test_v1_first_push_release_proof import _engine_consts
from test_v1_ssh_release_sig import _new_ssh_key, _ssh_block

TAG = "v1.0.0"
NEXT_TAG = "v1.0.1"
OLD_TAG = "v0.2.0"
SIGNERS = ".tess/keys/twiss-release-allowed-signers"
GPG_KEY_FILE = ".tess/keys/twiss-release-key.asc"
HAS_SSH = shutil.which("ssh-keygen") is not None


def _has_v020_tag() -> bool:
    r = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "-q", "--verify",
                        f"refs/tags/{OLD_TAG}^{{commit}}"], capture_output=True, text=True)
    return r.returncode == 0


pytestmark = pytest.mark.skipif(
    not (HAS_GIT and HAS_GPG and HAS_SSH and _has_v020_tag()),
    reason="Tess OS source repo with the v0.2.0 tag, git, gpg and ssh-keygen only")


def _run(cmd, cwd, env=None, ok=True, stdin=None):
    r = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, input=stdin)
    if ok:
        assert r.returncode == 0, f"{cmd}:\n{r.stdout[-4000:]}\n{r.stderr[-4000:]}"
    return r


def _git(cwd, *a, env=None, ok=True):
    return _run(["git", *a], cwd, env=env, ok=ok).stdout.strip()


def _tessctl(inst: Path, *args, ok=True, stdin=None):
    env = {**os.environ, "TESS_ROOT": str(inst)}
    return _run([sys.executable, str(inst / ".tess/bin/tessctl"), *args], inst, env=env,
                ok=ok, stdin=stdin)


def _release_upstream(tmp: Path, ssh_fp: str, signers: str, gpg, ssh_key: Path) -> Path:
    """A bare upstream whose signed `v1.0.0` tag is this tree (tracked files,
    working-tree bytes) with the throwaway release keys pinned."""
    src = tmp / "src"
    files = _run(["git", "ls-files", "-z"], REPO_ROOT).stdout.split("\0")
    for rel in filter(None, files):
        if rel.startswith("create-tess/template/") or not os.path.lexists(REPO_ROOT / rel):
            continue
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / rel, src / rel, follow_symlinks=False)
    real_pgp, real_ssh = _engine_consts()
    eng = src / ".tess/bin/tessctl"
    eng.write_text(eng.read_text().replace(real_ssh, ssh_fp).replace(real_pgp, gpg.fpr))
    lock = src / ".tess/tess.lock"
    lock.write_text(lock.read_text().replace(real_ssh, ssh_fp).replace(real_pgp, gpg.fpr))
    (src / SIGNERS).write_text(signers)
    env = {**os.environ, "GNUPGHOME": gpg.home}
    (src / GPG_KEY_FILE).write_text(_run(["gpg", "--armor", "--export", gpg.fpr], src, env=env).stdout)
    _git(src, "init", "-q", "-b", "main")
    for k, v in (("user.email", "release@tess.test"), ("user.name", "Release"),
                 ("commit.gpgsign", "false"), ("tag.gpgsign", "false"),
                 ("user.signingkey", gpg.fpr)):
        _git(src, "config", k, v)
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "release 1.0.0")
    commit, tree = _git(src, "rev-parse", "HEAD"), _git(src, "rev-parse", "HEAD^{tree}")
    msg = tmp / "tagmsg"
    msg.write_text(f"Release {TAG}\n\n" + _ssh_block(ssh_key, TAG, commit, tree, tmp))
    _git(src, "tag", "-s", "--cleanup=verbatim", "-F", str(msg), TAG, env=env)
    # NEXT_TAG: the same release with a changed engine (for the self-update
    # that is committed and pushed on its own).
    eng.write_text(eng.read_text() + "\n# r6 e2e: release 1.0.1\n")
    lock.write_text(lock.read_text().replace("  version: 1.0.0\n", "  version: 1.0.1\n", 1)
                    .replace(f"  upstream_ref: {TAG}\n", f"  upstream_ref: {NEXT_TAG}\n", 1))
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "release 1.0.1")
    commit, tree = _git(src, "rev-parse", "HEAD"), _git(src, "rev-parse", "HEAD^{tree}")
    msg.write_text(f"Release {NEXT_TAG}\n\n" + _ssh_block(ssh_key, NEXT_TAG, commit, tree, tmp))
    _git(src, "tag", "-s", "--cleanup=verbatim", "-F", str(msg), NEXT_TAG, env=env)
    bare = tmp / "upstream.git"
    _git(tmp, "clone", "-q", "--bare", str(src), str(bare))
    shutil.rmtree(src)
    return bare


def _v020_install(tmp: Path, upstream: Path, gpg) -> Path:
    """What `npm create tess@0.2.0 --yes` produced: the v0.2.0 template,
    policy registries reset, the wizard's bake verbs run by the 0.2.0 engine,
    git initialised with the 0.2.0 gate hooks, then committed by the user."""
    inst = tmp / "inst"
    arch = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", "--format=tar", OLD_TAG,
                           "create-tess/template"], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(arch)) as tf:
        tf.extractall(str(tmp / "x"))
    shutil.move(str(tmp / "x" / "create-tess" / "template"), str(inst))
    # The wizard's policy reset (create-tess/src/policy-reset.js) + scoped re-pin.
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    loader = SourceFileLoader("tessctl_r6_up", str(REPO_ROOT / ".tess/bin/tessctl"))
    mod = module_from_spec(spec_from_loader("tessctl_r6_up", loader))
    loader.exec_module(mod)
    for rel in ("core/policy/policy.yaml", ".tess/core/policy/policy.yaml"):
        p = inst / rel
        p.write_text(mod._policy_reset_registries_text(p.read_text()))
    _tessctl(inst, "lock", "--regen", "--yes", "--only", ".tess/core/policy/policy.yaml")
    for verb in (["roster", "apply", "--", "founders"], ["set-operator", "--", "Alex"],
                 ["pathway", "--", "chief-of-staff"], ["render"]):
        _tessctl(inst, *verb)
    # This install tracks the local upstream and trusts the throwaway release key.
    lock = inst / ".tess/tess.lock"
    text = lock.read_text()
    text = re.sub(r"(?m)^  upstream: .*$", f"  upstream: {upstream}", text, count=1)
    text = re.sub(r"(?m)^  trusted_key_fingerprint: .*$", f"  trusted_key_fingerprint: {gpg.fpr}",
                  text, count=1)
    lock.write_text(text)
    env = {**os.environ, "GNUPGHOME": gpg.home}
    (inst / GPG_KEY_FILE).write_text(_run(["gpg", "--armor", "--export", gpg.fpr], inst,
                                          env=env).stdout)
    _git(inst, "init", "-q", "-b", "main")
    for k, v in (("user.email", "alex@tess.test"), ("user.name", "Alex"),
                 ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
        _git(inst, "config", k, v)
    _tessctl(inst, "gate", "install-hooks", ok=False)
    _git(inst, "add", "-A")
    _git(inst, "commit", "-q", "--no-verify", "-m", "Tess OS 0.2.0")
    origin = tmp / "origin.git"
    _git(tmp, "init", "-q", "-b", "main", "--bare", str(origin))
    _git(inst, "remote", "add", "origin", str(origin))
    _git(inst, "push", "-q", "--no-verify", "origin", "main")
    return inst


@pytest.fixture(scope="module")
def upgraded(tmp_path_factory, gpg_key):
    tmp = tmp_path_factory.mktemp("r6up")
    mp = pytest.MonkeyPatch()
    home = tmp / "oshome"
    home.mkdir(mode=0o700)
    use_os_home(mp, home)
    try:
        key, ssh_fp, signers = _new_ssh_key(tmp / "keys", "release")
        upstream = _release_upstream(tmp, ssh_fp, signers, gpg_key, key)
        inst = _v020_install(tmp, upstream, gpg_key)
        seed = _git(inst, "rev-parse", "HEAD")
        su = _tessctl(inst, "self-update", "--ref", TAG, ok=False)
        rc, up_out = run_tessctl_in_pty(inst, "update", "--ref", TAG, answer=f"accept {TAG}",
                                        prompt=b"accept> ")
        yield {"inst": inst, "tmp": tmp, "seed": seed, "self_update": su, "update_rc": rc,
               "update_out": up_out, "origin": tmp / "origin.git", "ssh_fp": ssh_fp,
               "signers": signers, "gpg_fpr": gpg_key.fpr}
    finally:
        mp.undo()


def _hook_commands(inst: Path) -> list:
    """Every hook command .claude/settings.json and .codex/config.toml (and a
    .codex/hooks.json, when one exists) carry."""
    cmds = []
    docs = [json.loads((inst / ".claude/settings.json").read_text())]
    if (inst / ".codex/hooks.json").is_file():
        docs.append(json.loads((inst / ".codex/hooks.json").read_text()))
    for doc in docs:
        for groups in (doc.get("hooks") or {}).values():
            for g in groups:
                cmds += [h["command"] for h in g.get("hooks", []) if h.get("type") == "command"]
    toml = (inst / ".codex/config.toml").read_text()
    cmds += [json.loads(m) for m in re.findall(r'(?m)^command = ("(?:[^"\\]|\\.)*")$', toml)]
    return cmds


def _scripts_run(cmds: list) -> set:
    """Project-relative files the hook commands execute (the launcher and the
    script after `--`) plus `closure:<dir>` for each --closure directory."""
    out = set()
    for c in cmds:
        if "run-pinned.py" in c:
            out.add(".claude/hooks/run-pinned.py")
        m = re.search(r" -- (\S+)", c)
        if m:
            out.add(m.group(1).strip("'\""))
        out |= {"closure:" + d for d in re.findall(r"--closure (\S+)", c)}
    return out


def test_self_update_then_update_succeed(upgraded):
    su = upgraded["self_update"]
    assert su.returncode == 0, su.stdout[-3000:] + su.stderr[-3000:]
    assert upgraded["update_rc"] == 0, upgraded["update_out"][-6000:]
    assert "Step 6.6: install Tess's hook and brain files" in upgraded["update_out"]


def test_release_owned_paths_are_adopted(upgraded):
    """Integration pass 3: 1.0.0 owns `.codex/rules/tess.rules` and
    `.agents/skills/security-audit/**`; a 0.2.0 manifest did not, so the
    render skipped them. The update adds exactly the release's new owned
    globs and renders them."""
    inst = upgraded["inst"]
    manifest = json.loads((inst / "tess.manifest.json").read_text())
    release = json.loads((REPO_ROOT / "tess.manifest.json").read_text())
    for g in (".codex/rules/tess.rules", ".agents/skills/security-audit/**"):
        assert g in manifest["owned_globs"], manifest["owned_globs"]
    assert set(manifest["owned_globs"]) <= set(release["owned_globs"]), \
        "only globs the release manifest owns are added"
    assert "Tess OS command rules for Codex" in (inst / ".codex/rules/tess.rules").read_text()
    shipped = sorted(p.name for p in (REPO_ROOT / ".agents/skills/security-audit").iterdir())
    got = sorted(p.name for p in (inst / ".agents/skills/security-audit").iterdir())
    assert got == shipped
    assert "Tess now manages .codex/rules/tess.rules" in upgraded["update_out"]


def test_the_release_ssh_trust_root_is_added_and_the_openpgp_pin_kept(upgraded, engine):
    """Integration pass 3: the signed release's SSH release key is ADDED (pin
    + allowed_signers file); the OpenPGP pin the install trusted is unchanged."""
    inst = upgraded["inst"]
    fw = engine.load_lock(inst)["framework"]
    assert fw["trusted_ssh_key_fingerprint"] == upgraded["ssh_fp"]
    assert fw["trusted_key_fingerprint"] == upgraded["gpg_fpr"]
    assert (inst / SIGNERS).read_text() == upgraded["signers"]
    assert "pinned the SSH release key" in upgraded["update_out"]


def _path_without_gpg(tmp: Path) -> str:
    """A PATH holding every program of the current PATH except gpg."""
    shim = tmp / "nogpg-bin"
    if not shim.is_dir():
        shim.mkdir()
        for d in os.environ.get("PATH", "").split(os.pathsep):
            if not d or not os.path.isdir(d):
                continue
            for name in os.listdir(d):
                if name.startswith("gpg") or (shim / name).exists():
                    continue
                src = os.path.join(d, name)
                if os.path.isfile(src) and os.access(src, os.X_OK):
                    os.symlink(src, shim / name)
    return str(shim)


def test_every_hook_script_is_installed_with_its_pinned_sha(upgraded, engine):
    """GPT-6 #1: before the fix run-pinned.py, tess-gate.py and
    scripts/brain/tessbrain.py (+ brainlib) were missing while the rendered
    configs ran them, and the older copies left behind no longer matched the
    advanced pins."""
    inst = upgraded["inst"]
    pins = engine._pinned_scripts_parse((inst / ".tess/core/pinned-scripts.sha256").read_text())
    run = _scripts_run(_hook_commands(inst))
    assert {".claude/hooks/run-pinned.py", ".claude/hooks/tess-gate.py",
            "scripts/brain/tessbrain.py", "scripts/brain/onboard.py",
            "closure:scripts/brain"} <= run, run
    lock = engine.load_lock(inst)
    live_pins = {a["live_path"]: a["base_sha"] for a in lock["files"].values()
                 if isinstance(a, dict) and a.get("live_path")}
    for rel in sorted(run):
        if rel.startswith("closure:"):
            for py in (inst / rel[len("closure:"):]).rglob("*.py"):
                r = py.relative_to(inst).as_posix()
                assert r in pins, f"{r}: unpinned code in a hook closure"
            continue
        path = inst / rel
        assert path.is_file() and not path.is_symlink(), f"{rel} is missing"
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        want = pins.get(rel) or (live_pins.get(rel) or "").replace("sha256:", "")
        assert got == want, f"{rel}: installed bytes are not the pinned release bytes"
    for rel, want in pins.items():
        assert hashlib.sha256((inst / rel).read_bytes()).hexdigest() == want, rel
    assert engine._pinned_runtime_findings(inst) == []
    assert (inst / "scripts/tess").read_bytes() == (REPO_ROOT / "scripts/tess").read_bytes()


def test_verify_lock_check_and_hooks_status_work(upgraded):
    inst = upgraded["inst"]
    for args in (["verify"], ["lock", "--check"]):
        r = _tessctl(inst, *args, ok=False)
        assert r.returncode == 0, f"{args}: {r.stdout[-3000:]} {r.stderr[-2000:]}"
    r = _run([sys.executable, "-I", "-B", "scripts/tess", "hooks-status", "--runtime", "claude"],
             inst, ok=False)
    assert r.returncode in (0, 1, 3), r.stdout + r.stderr
    assert "usage" not in (r.stdout + r.stderr).lower()


def _claude_gate(inst: Path, command: str):
    cmd = next(c for c in _hook_commands(inst) if "tess-gate.py --runtime claude" in c)
    payload = {"hook_event_name": "PreToolUse", "session_id": "r6", "tool_name": "Bash",
               "tool_input": {"command": command}, "cwd": str(inst)}
    r = subprocess.run(["sh", "-c", cmd], input=json.dumps(payload), capture_output=True,
                       text=True, cwd=str(inst), timeout=120,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(inst)})
    if r.returncode == 2:
        return "deny", r.stderr
    assert r.returncode == 0, r.stderr
    if not r.stdout.strip():
        return "allow", ""
    out = json.loads(r.stdout)["hookSpecificOutput"]
    return out["permissionDecision"], out.get("permissionDecisionReason", "")


def test_the_installed_gate_hook_evaluates_calls(upgraded):
    inst = upgraded["inst"]
    decision, why = _claude_gate(inst, "ls -la")
    assert decision == "allow", why
    decision, why = _claude_gate(inst, "rm -f CLAUDE.md")
    assert decision == "deny", why


def test_the_first_push_after_the_update_needs_no_verdict(upgraded):
    """GPT-6 #2: the committed update (new engine, its 0.2.0 backup, the new
    hook and brain files, core, lock) passes the push gate on the release
    proof alone: an explicit gate run, then a real `git push`."""
    _commit_and_push(upgraded, "Update Tess OS to 1.0.0", engine_only=False)


def _commit_and_push(upgraded, message: str, engine_only: bool) -> str:
    """Commit everything, run the pre-push gate against origin/main, then a
    real `git push` (the installed pre-push hook runs too)."""
    inst = upgraded["inst"]
    status = _git(inst, "status", "--porcelain")
    assert "D .tess/staging/.gitkeep" not in status, status
    base = _git(upgraded["origin"], "rev-parse", "main")
    _git(inst, "add", "-A")
    _git(inst, "commit", "-q", "-m", message)
    head = _git(inst, "rev-parse", "HEAD")
    r = _tessctl(inst, "gate", "pre-push", "--json", ok=False,
                 stdin=f"refs/heads/main {head} refs/heads/main {base}\n")
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["blocked"] is False, out
    assert out["release_proof"]["status"] == "accepted", out
    assert bool(out["release_proof"].get("engine_only")) is engine_only, out
    push = _run(["git", "push", "origin", "main"], inst, ok=False)
    assert push.returncode == 0, push.stdout + push.stderr
    assert _git(upgraded["origin"], "rev-parse", "main") == head
    return head


def _ensure_100_pushed(upgraded) -> None:
    if _git(upgraded["origin"], "rev-parse", "main") == upgraded["seed"]:
        _commit_and_push(upgraded, "Update Tess OS to 1.0.0", engine_only=False)


def test_a_self_update_committed_on_its_own_pushes_then_the_update(upgraded, engine):
    """GPT-6 #2, second half: `self-update` (now the 1.0.0 engine) committed
    and pushed BEFORE `update`. The lock records engine_ref / engine_commit;
    the gate accepts exactly that engine transition, then the update."""
    inst = upgraded["inst"]
    _ensure_100_pushed(upgraded)
    su = _tessctl(inst, "self-update", "--ref", NEXT_TAG, ok=False)
    assert su.returncode == 0, su.stdout[-3000:] + su.stderr[-3000:]
    fw = engine.load_lock(inst)["framework"]
    assert (fw["version"], fw["upstream_ref"], fw["engine_ref"]) == ("1.0.0", NEXT_TAG, NEXT_TAG)
    assert re.fullmatch(r"[0-9a-f]{40}", fw["engine_commit"])
    _commit_and_push(upgraded, "Tess engine 1.0.1", engine_only=True)
    # Integration pass 3: with the SSH release key adopted by the 1.0.0
    # update, this update verifies with ssh-keygen alone (no gpg on PATH).
    no_gpg = _path_without_gpg(upgraded["tmp"])
    assert shutil.which("gpg", path=no_gpg) is None and shutil.which("ssh-keygen", path=no_gpg)
    rc, out = run_tessctl_in_pty(inst, "update", "--ref", NEXT_TAG, answer=f"accept {NEXT_TAG}",
                                 prompt=b"accept> ",
                                 env=operator_env(TESS_ROOT=str(inst), PATH=no_gpg))
    assert rc == 0, out[-4000:]
    assert "SSH release signature OK" in out, out[-4000:]
    fw = engine.load_lock(inst)["framework"]
    assert (fw["version"], fw["engine_ref"], fw["upstream_commit"]) == (
        "1.0.1", NEXT_TAG, fw["engine_commit"])
    _commit_and_push(upgraded, "Update Tess OS to 1.0.1", engine_only=False)


