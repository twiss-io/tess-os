"""`onboard.py apply` / `add` / `add-mode` / `convert-clone` (spec 6.4, 8, 9.3, G13, G14).

Create-only and idempotent: a second apply is a no-op with a clean
`git status`; existing bytes are never touched; the first decision carries
the operator's verbatim step-1 answer; commits are seed-or-path-scoped and
nothing is pushed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import _brain_oobe_helpers as h


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_apply_seed_commit_decision_probe_and_private_dir(tmp_path):
    root = h.mini_instance(tmp_path)
    done = h.onboard_fixture(root, "agency-solo")
    assert done.returncode == 0, done.stderr
    brain = json.loads((root / "brain" / "brain.json").read_text())
    assert brain["onboarding"]["status"] == "complete" and brain["onboarding"]["completed_at"]
    assert brain["entity_roots"] == ["brain/agency", "brain/clients/*"]
    assert brain["identity"] == {"operator_name": "Mira Okafor", "operator_slug": "mira-okafor",
                                 "assistant_name": "Tess", "pathway": "chief-of-staff"}
    owner, jon = brain["principals"]
    assert owner["role"] == "owner" and owner["scope"] == ["**"] and owner["decides"] is True
    assert jon["slug"] == "jon-park" and jon["scope"] == ["clients/northwind-studio/**"]
    assert brain["capture"]["journal"] == "commit-redacted" and brain["presets"] == ["solo-consultant"]
    dec = (root / "brain" / "decisions" / "D-20260924-1015-brain-mode.md").read_text()
    assert "status: pending-verification" in dec and "detected_by: onboarding" in dec
    assert 'source_quote: "An agency: I run a small consultancy serving outside clients."' in dec
    probe = json.loads((root / "brain" / "probe.json").read_text())
    ids = {q["id"]: q["expect"] for q in probe["questions"]}
    assert ids["entities"] == ["agency", "clients/bluefin-labs", "clients/northwind-studio"]
    assert ids["first-decision"]["id"] == "D-20260924-1015-brain-mode"
    assert (root / "brain" / ".private" / ".gitignore").read_text() == "*\n"
    log = h.git(root, "log", "--format=%s").stdout
    assert "brain" in log.lower()
    assert h.git(root, "status", "--porcelain").stdout == ""


def test_second_apply_is_a_noop(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "personal").returncode == 0
    head = h.git(root, "rev-parse", "HEAD").stdout
    before = {p: sha(root / p) for p in h.tree(root)}
    again = h.onboard(root, "apply")
    assert again.returncode == 0 and "created 0 file(s)" in again.stdout
    assert {p: sha(root / p) for p in h.tree(root)} == before
    assert h.git(root, "rev-parse", "HEAD").stdout == head
    assert h.git(root, "status", "--porcelain").stdout == ""


def test_apply_never_overwrites_existing_files(tmp_path):
    root = h.mini_instance(tmp_path)
    custom = root / "brain" / "START-HERE.md"
    custom.parent.mkdir(parents=True)
    custom.write_text("# my own map\n\n## Entities\n| Entity | Kind | Start here |\n|---|---|---|\n")
    h.onboard(root, "init", "--non-interactive", "--answers", str(h.FIXTURES / "answers-personal.json"))
    assert h.onboard(root, "apply").returncode == 0
    text = custom.read_text()
    assert text.startswith("# my own map"), "hand-written text kept"
    assert "[brain/life/AGENTS.md](life/AGENTS.md)" in text, "index row appended"


def test_apply_path_scoped_commit_leaves_unrelated_work_alone(tmp_path):
    root = h.mini_instance(tmp_path)
    (root / "notes.txt").write_text("seed\n")
    h.git(root, "add", "-A")
    h.git(root, "commit", "-qm", "pre-existing")
    (root / "notes.txt").write_text("unrelated edit\n")
    assert h.onboard_fixture(root, "personal").returncode == 0
    last = h.git(root, "show", "--name-only", "--format=%s", "HEAD").stdout.split("\n")
    assert last[0].startswith("brain: onboarding apply")
    assert all(p.startswith(("brain/", ".gitignore", "memory/")) for p in last[1:] if p)
    assert h.git(root, "status", "--porcelain").stdout.strip() == "M notes.txt"


def test_dry_run_writes_nothing(tmp_path):
    root = h.mini_instance(tmp_path)
    h.onboard(root, "init", "--non-interactive", "--answers", str(h.FIXTURES / "answers-personal.json"))
    before = sorted(p.as_posix() for p in root.rglob("*") if ".git/" not in p.as_posix())
    done = h.onboard(root, "apply", "--dry-run", "--json")
    assert done.returncode == 0
    assert "brain/life/AGENTS.md" in json.loads(done.stdout)["created"]
    after = sorted(p.as_posix() for p in root.rglob("*") if ".git/" not in p.as_posix())
    assert before == after


def test_add_is_create_only_and_indexes_first(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    acme = root / "brain" / "clients" / "acme" / "AGENTS.md"
    acme.parent.mkdir(parents=True)
    acme.write_text("custom\n")
    before = sha(acme)
    done = h.onboard(root, "add", "client", "Acme")
    assert done.returncode == 0 and "skipped (exists): brain/clients/acme/AGENTS.md" in done.stdout
    assert sha(acme) == before
    assert "[brain/clients/acme/AGENTS.md](clients/acme/AGENTS.md)" in (root / "brain" / "START-HERE.md").read_text()
    assert (root / "brain" / "clients" / "acme" / "CLAUDE.md").read_text() == "@AGENTS.md\n"
    person = h.onboard(root, "add", "person", "Dana Reyes")
    assert person.returncode == 0
    assert "[people/dana-reyes.md](people/dana-reyes.md)" in (root / "brain" / "agency" / "AGENTS.md").read_text()
    proj = h.onboard(root, "add", "project", "Pricing Revamp")
    assert proj.returncode == 2 and "--in" in proj.stderr
    ok = h.onboard(root, "add", "project", "Pricing Revamp", "--in", "northwind-studio")
    assert ok.returncode == 0
    assert (root / "brain/clients/northwind-studio/projects/pricing-revamp/AGENTS.md").exists()


def test_add_mode_never_moves_and_records_decision(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    before = {p: sha(root / p) for p in h.tree(root) if not p.endswith(("brain.json", "START-HERE.md"))}
    done = h.onboard(root, "add-mode", "personal", "--quote", "Add my personal life too.")
    assert done.returncode == 0, done.stderr
    brain = json.loads((root / "brain" / "brain.json").read_text())
    assert brain["modes"] == ["agency", "personal"]
    assert "brain/life/areas/*" in brain["entity_roots"]
    decs = list((root / "brain" / "decisions").glob("D-*-add-mode-personal.md"))
    assert len(decs) == 1 and "Add my personal life too." in decs[0].read_text()
    assert all(sha(root / p) == s for p, s in before.items()), "nothing moved or rewritten"
    assert "- Mode: agency, personal (primary: agency)." in (root / "brain" / "START-HERE.md").read_text()
    assert h.onboard(root, "apply").returncode == 0
    assert json.loads((root / "brain" / "brain.json").read_text())["modes"] == ["agency", "personal"]


def test_convert_clone_renames_framework_origin(tmp_path):
    root = h.mini_instance(tmp_path, source_repo=True)
    h.git(root, "remote", "add", "origin", "git@github.com:twiss-io/tess-os.git")
    plan = h.onboard(root, "convert-clone")
    assert plan.returncode == 0 and "rename remote origin -> upstream" in plan.stdout
    assert h.git(root, "remote").stdout.split() == ["origin"], "no change without --yes"
    done = h.onboard(root, "convert-clone", "--yes")
    assert done.returncode == 0, done.stderr
    assert h.git(root, "remote").stdout.split() == ["upstream"]
    st = json.loads(h.onboard(root, "status", "--json").stdout)
    assert st["status"] == "pending"
    again = h.onboard(root, "convert-clone", "--yes")
    assert again.returncode == 3, "only a source-repo clone converts"


def test_learn_tool_runs_as_subprocess_when_present(tmp_path):
    root = h.mini_instance(tmp_path)
    marker = root / "learn-calls.txt"
    (root / "scripts" / "brain" / "tessbrain.py").write_text(
        "import sys, pathlib\n"
        "pathlib.Path(%r).open('a').write(' '.join(sys.argv[1:]) + '\\n')\n" % str(marker))
    h.onboard(root, "init", "--non-interactive", "--answers", str(h.FIXTURES / "answers-personal.json"))
    done = h.onboard(root, "apply", extra_env={"TESS_BRAIN_NO_LEARN": ""})
    assert done.returncode == 0, done.stderr
    assert marker.read_text().splitlines() == ["index --quiet", "githooks install"]
