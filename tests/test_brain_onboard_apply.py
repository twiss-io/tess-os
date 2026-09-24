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
    assert 'status: "pending-verification"' in dec and 'detected_by: "onboarding"' in dec
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
    moving = ("brain.json", "START-HERE.md", "probe.json")  # indexes/expectations, never content
    before = {p: sha(root / p) for p in h.tree(root) if not p.endswith(moving)}
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


def test_convert_clone_keeps_a_private_origin_without_a_remote_add_hint(tmp_path):
    root = h.mini_instance(tmp_path, source_repo=True)
    h.git(root, "remote", "add", "origin", "git@example.invalid:someone/my-private-brain.git")
    done = h.onboard(root, "convert-clone", "--yes")
    assert done.returncode == 0, done.stderr
    assert h.git(root, "remote").stdout.split() == ["origin"]
    assert "keep origin (already set to git@example.invalid:someone/my-private-brain.git)" in done.stdout
    assert "git remote add origin" not in done.stdout


def test_add_warns_when_start_here_goes_over_budget(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    quiet = h.onboard(root, "add", "client", "Northwind")
    assert quiet.returncode == 0 and "over its budget" not in quiet.stderr
    bj = root / "brain" / "brain.json"
    brain = json.loads(bj.read_text())
    brain["budgets"]["start_here_lines"] = 10
    bj.write_text(json.dumps(brain, indent=2) + "\n")
    loud = h.onboard(root, "add", "client", "Globex")
    assert loud.returncode == 0, loud.stderr
    assert "brain/START-HERE.md is" in loud.stderr and "over its budget (10 lines" in loud.stderr


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


# The one record format is ws-learn's (brainlib/records.py). Onboarding ships no record template
# of its own: it writes ws-learn's shape, and uses ws-learn's body template whenever it exists.
DECISION_KEYS = ["schema", "id", "type", "kind", "title", "status", "tier", "authority", "decided_by",
                 "decider_seat", "entity", "consulted", "informed", "source_quote", "also_quoted",
                 "source_speaker", "source_at", "source_ref", "source_session", "approves_quote",
                 "delegation_ref", "detected_by", "confirmed", "verified", "verified_at", "supersedes",
                 "superseded_by", "tags"]


def _front_matter(text: str):
    assert text.startswith("---\n")
    block, body = text[4:].split("\n---\n", 1)
    pairs = [line.split(": ", 1) for line in block.splitlines()]
    return [k for k, _ in pairs], {k: json.loads(v) for k, v in pairs}, body


def test_decision_uses_the_single_learn_record_format(tmp_path):
    # templates/records/** belongs to ws-learn; the body below is FALLBACK_BODY or ws-learn's
    # decision template, which share these section lines (either may be installed).
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    keys, meta, body = _front_matter(
        (root / "brain" / "decisions" / "D-20260924-1015-brain-mode.md").read_text())
    assert keys == DECISION_KEYS  # every value is JSON-encoded, keys in ws-learn's order
    assert meta["status"] == "pending-verification" and meta["detected_by"] == "onboarding"
    assert meta["confirmed"] is False and meta["verified"] is False and meta["tags"] == ["onboarding"]
    assert meta["source_quote"] == "An agency: I run a small consultancy serving outside clients."
    assert body.startswith("\n# Brain mode: agency\n\n## Context\n")
    assert "> An agency: I run a small consultancy serving outside clients.\n" in body
    assert "\n## Decision\n\nWe will run this brain as: agency (primary: agency)." in body
    assert "\n## Consequences\n\n- Entity roots: brain/agency, brain/clients/*." in body


def test_decision_body_comes_from_the_learn_template_when_present(tmp_path):
    root = h.mini_instance(tmp_path)
    tpl = root / "scripts" / "brain" / "templates" / "record-bodies" / "decision.md"
    tpl.parent.mkdir(parents=True, exist_ok=True)
    tpl.write_text("\n# {title}\n\nLEARN-TEMPLATE {quote}\n")
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    text = (root / "brain" / "decisions" / "D-20260924-1015-brain-mode.md").read_text()
    assert text.endswith("\n---\n\n# Brain mode: agency\n\nLEARN-TEMPLATE "
                         "An agency: I run a small consultancy serving outside clients.\n")


def test_decision_round_trips_through_learn_frontmatter_when_installed(tmp_path):
    """After integration (ws-learn merged), its own parser + writer reproduce the file byte for byte."""
    import sys
    lib = h.BRAIN_TOOLS / "brainlib" / "frontmatter.py"
    if not lib.exists():
        import pytest
        pytest.skip("ws-learn (scripts/brain/brainlib) is not in this tree")
    sys.path.insert(0, str(h.BRAIN_TOOLS))
    try:
        from brainlib import frontmatter, records  # type: ignore
    finally:
        sys.path.pop(0)
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    path = root / "brain" / "decisions" / "D-20260924-1015-brain-mode.md"
    text = path.read_text()
    _, meta, body = _front_matter(text)
    assert frontmatter.dump(meta, body, records.ORDER["decision"]) == text  # ws-learn's writer, same bytes
    rec = records.load(path)  # ws-learn's reader sees what its sync re-verification needs
    assert (rec.id, rec.status, rec.kind) == ("D-20260924-1015-brain-mode", "pending-verification", "decision")
    assert rec.meta["detected_by"] == "onboarding"
    assert rec.meta["source_quote"] == "An agency: I run a small consultancy serving outside clients."


# ---- names: non-Latin scripts, collisions, empty names, table escaping --------------------

def _agency_with_clients(tmp_path, clients):
    data = json.loads((h.FIXTURES / "answers-agency-solo.json").read_text())
    for item in data["answers"]:
        if item["field"] == "clients":
            item["value"] = clients
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(data, ensure_ascii=False))
    root = h.mini_instance(tmp_path)
    assert h.onboard(root, "init", "--non-interactive", "--answers", str(path)).returncode == 0
    return root


def test_non_latin_clients_at_onboarding_each_get_their_own_entity(tmp_path):
    root = _agency_with_clients(tmp_path, ["\u5317\u4eac\u54a8\u8be2", "\u4e0a\u6d77\u8d38\u6613"])
    assert h.onboard(root, "apply").returncode == 0
    dirs = sorted(p.name for p in (root / "brain" / "clients").iterdir())
    assert len(dirs) == 2 and all(d.startswith("e-") for d in dirs), dirs
    start = (root / "brain" / "START-HERE.md").read_text()
    assert "| \u5317\u4eac\u54a8\u8be2 | client |" in start and "| \u4e0a\u6d77\u8d38\u6613 | client |" in start
    assert "item" not in dirs


def test_add_never_reports_another_entity_as_existing(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    seen = set()
    for name in ("\u6771\u4eac\u5546\u4e8b", "\u041c\u043e\u0441\u043a\u0432\u0430 \u0413\u0440\u0443\u043f\u043f",
                 "\u0634\u0631\u0643\u0629", "Caf\u00e9", "Cafe"):
        done = h.onboard(root, "add", "client", name)
        assert done.returncode == 0 and "skipped (exists)" not in done.stdout, (name, done.stdout)
        dest = done.stdout.strip().splitlines()[-1].split(" -> ")[1].split(" ")[0]
        assert dest not in seen
        seen.add(dest)
    assert "brain/clients/cafe-2" in seen
    again = h.onboard(root, "add", "client", "Caf\u00e9")
    assert again.returncode == 0 and "skipped (exists): brain/clients/cafe/AGENTS.md" in again.stdout


def test_add_rejects_empty_names_and_escapes_table_pipes(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    for bad in ("", "   ", "..."):
        done = h.onboard(root, "add", "client", bad)
        assert done.returncode == 2 and "no letters or digits" in done.stderr, bad
    assert h.onboard(root, "add", "client", "Foo | Bar").returncode == 0
    assert "| Foo \\| Bar | client |" in (root / "brain" / "START-HERE.md").read_text()
