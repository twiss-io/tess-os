"""Acceptance L10 + status (spec 10.9): saved = owning folder + linked from
START HERE + committed + pushed, checked by a tool; hooks never bypassed."""
import json
import subprocess
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib


@pytest.fixture
def inst(tmp_path):
    bj = json.loads(Path(fxlib.HERE, "brain.json").read_text())
    bj["save"]["autopush"] = True
    p = tmp_path / "bj.json"
    p.write_text(json.dumps(bj))
    inst = Path(fxlib.make(str(tmp_path / "fx"), brain_json=str(p)))
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    fxlib.run(str(inst), "remote", "add", "origin", str(bare))
    fxlib.run(str(inst), "push", "-q", "-u", "origin", "main")  # the harness seed push
    return inst


def save(inst, *args):
    r = fxlib.cli(inst, "--json", "save", *args)
    return r.returncode, json.loads(r.stdout or "{}")


def test_unlinked_file_is_not_saved_and_the_link_is_named(inst):
    note = inst / "brain/clients/acme/notes.md"
    note.write_text("# Acme notes\n")
    rc, out = save(inst, "-m", "probe")
    assert rc == 1 and "brain/clients/acme/notes.md (add a link to it in brain/clients/acme/AGENTS.md)" in out["error"]


def test_linked_file_one_commit_only_brain_paths_and_pushed(inst, tmp_path):
    (inst / "brain/clients/acme/notes.md").write_text("# Acme notes\n")
    agents = inst / "brain/clients/acme/AGENTS.md"
    agents.write_text(agents.read_text().replace("| Decisions | decisions/INDEX.md |",
                                                 "| Decisions | decisions/INDEX.md |\n| Notes | [notes.md](notes.md) |"))
    (inst / "memory/projects/clients-acme--site.md").write_text("---\nentity: clients/acme\n---\n# Site\n")
    (inst / "stray.txt").write_text("not brain\n")
    head0 = fxlib.run(str(inst), "rev-parse", "HEAD").stdout.strip()
    rc, out = save(inst, "-m", "probe")
    assert rc == 0 and out["pushed"] is True, json.dumps(out)
    assert fxlib.run(str(inst), "rev-list", "--count", head0 + "..HEAD").stdout.strip() == "1"
    names = fxlib.run(str(inst), "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert names and all(n.startswith(("brain/", "memory/projects/")) for n in names), names
    assert "stray.txt" not in names
    remote = subprocess.run(["git", "-C", str(tmp_path / "bare.git"), "rev-parse", "main"], capture_output=True,
                            text=True).stdout.strip()
    assert remote == fxlib.run(str(inst), "rev-parse", "HEAD").stdout.strip()
    st = json.loads(fxlib.cli(inst, "status", "--json").stdout)
    assert st["unsaved"] == [] and st["unpushed"] == 0 and st["unreachable"] == []


def test_framework_remote_is_refused(inst):
    fxlib.run(str(inst), "remote", "set-url", "origin", "git@github.com:twiss-io/tess-os.git")
    (inst / "brain/decisions").mkdir(exist_ok=True)
    rc, out = save(inst, "-m", "probe")
    assert rc == 0 and out["pushed"] is False
    assert any("public Tess OS framework repo" in n for n in out["notes"])


def test_no_hook_bypass_anywhere_in_the_tools():
    hits = subprocess.run(["grep", "-rn", "--", "--no-verify", str(Path(fxlib.REPO) / "scripts" / "brain")],
                          capture_output=True, text=True).stdout
    assert hits == ""


def test_repository_hooks_run_and_can_refuse(inst):
    hook = Path(fxlib.run(str(inst), "rev-parse", "--git-path", "hooks").stdout.strip())
    hook = hook if hook.is_absolute() else inst / hook
    hook.mkdir(parents=True, exist_ok=True)
    (hook / "pre-commit").write_text("#!/bin/sh\necho gate says no >&2\nexit 1\n")
    (hook / "pre-commit").chmod(0o755)
    fxlib.sync_fixture(inst)
    rc, out = save(inst, "-m", "probe")
    assert rc == 1 and "gate says no" in out["error"]


def test_status_flags_misplaced_unsaved_and_learning(inst):
    (inst / "kb/research").mkdir(parents=True)
    (inst / "kb/research/2026-09-24-market.md").write_text("# research in the old place\n")
    fxlib.sync_fixture(inst)
    st = json.loads(fxlib.cli(inst, "status", "--json").stdout)
    assert "kb/research/2026-09-24-market.md" in st["misplaced"]
    assert st["unsaved"] and st["inbox"] == 1 and st["records"] >= 5
    text = fxlib.cli(inst, "status").stdout
    assert "NOT SAVED" in text and "move to brain/" in text


def test_githooks_install_is_idempotent_and_keeps_existing_hooks(inst):
    hook = inst / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\n# gate block\nexit 0\n")
    hook.chmod(0o755)
    first = json.loads(fxlib.cli(inst, "--json", "githooks", "install").stdout)
    second = json.loads(fxlib.cli(inst, "--json", "githooks", "install").stdout)
    assert first == {"pre-commit": "installed", "post-merge": "installed"}
    assert second == {"pre-commit": "present", "post-merge": "present"}
    text = hook.read_text()
    assert text.count("# tess-brain-guard v1") == 1 and "# gate block" in text and "lint --staged --warn-only" in text
