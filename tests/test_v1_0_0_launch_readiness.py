"""1.0.0 (phase 3): launch readiness, and app code under the ship gate.

Apps built quickly with AI agents have cost their owners money or lawsuits in
the first week: a metered hosting or AI bill with no cap, a function that
triggers itself, row-level security that was never on, bulk messages without
consent, a site keyboard users cannot use, a release nobody audited. The
contract tested here:

  * `tessctl launch init` writes launch-readiness.json with all six items
    open; `check` lists them; `mark-launched` is refused while any item is
    open, invalid or missing, or while the production rule is still the
    shipped __REPLACE_ME__ placeholder;
  * an item is answered only by "done" with real evidence (evidence files must
    exist inside the project) or "n/a" with a reason; a missing item is open;
  * while "preparing" the record is advisory (exit 0, a doctor warning); once
    "launched" with anything unanswered, `launch check` and `doctor` exit 1
    and the ship gate refuses the push, reading the record from the pushed
    commit; an unreadable record is treated as launched;
  * the refusal crosses the public projection as LAUNCH_READINESS_INCOMPLETE,
    never INTERNAL_ERROR_REDACTED, and names no item or path in CI;
  * `doctor` warns while a policy rule still holds the placeholder glob.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import _brain_oobe_helpers as h

REPO = Path(__file__).resolve().parent.parent
HAS_GIT = shutil.which("git") is not None
pytestmark = pytest.mark.skipif(not HAS_GIT, reason="needs git")

GOOD_EVIDENCE = "Checked in the hosting dashboard: hard bandwidth cap at 100 GB."


def _tessctl(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "TESS_ROOT": str(root), "CODEX_HOME": str(root / ".no-codex-home")}
    env.pop("TESS_VERBOSE", None)
    return subprocess.run([sys.executable, "-I", "-B", str(root / ".tess" / "bin" / "tessctl"), *args],
                          cwd=str(root), env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _commit(root: Path, msg: str, *paths: str) -> str:
    _git(root, "add", "--", *paths)
    _git(root, "-c", "user.email=t@tess.test", "-c", "user.name=T", "-c", "commit.gpgsign=false",
         "commit", "-q", "--no-verify", "-m", msg, "--", *paths)
    return _git(root, "rev-parse", "HEAD")


def _answered(engine, **over) -> dict:
    doc = engine._launch_template()
    for iid in engine.LAUNCH_ITEM_IDS:
        doc["items"][iid] = {"status": "done", "evidence": GOOD_EVIDENCE, "evidence_files": []}
    doc["items"]["messaging-consent"] = {"status": "n/a",
                                         "reason": "The app sends no SMS, email or calls at all."}
    for k, v in over.items():
        doc[k] = v
    return doc


def _ev(engine, doc, exists=lambda rel: False, placeholders=()):
    text = doc if isinstance(doc, str) else json.dumps(doc)
    return engine._launch_evaluate(text, exists, placeholders)


# ── the evaluator ─────────────────────────────────────────────────────────


def test_template_has_every_item_open_and_is_advisory(engine):
    doc = engine._launch_template()
    assert set(doc["items"]) == set(engine.LAUNCH_ITEM_IDS) and len(engine.LAUNCH_ITEM_IDS) == 6
    assert set(engine.LAUNCH_ITEM_IDS) == {"spend-limits", "self-trigger-guards", "public-key-data-access",
                                           "messaging-consent", "accessibility", "security-audit"}
    ev = _ev(engine, doc)
    assert ev["status"] == "preparing" and not ev["blocking"]
    assert ev["open"] == list(engine.LAUNCH_ITEM_IDS) and ev["errors"] == []


def test_launched_with_open_items_fails_closed(engine):
    doc = engine._launch_template()
    doc["status"] = "launched"
    ev = _ev(engine, doc)
    assert ev["blocking"] and len(ev["open"]) == 6


def test_launched_and_fully_answered_passes(engine):
    ev = _ev(engine, _answered(engine, status="launched"))
    assert not ev["blocking"] and ev["open"] == [] and ev["invalid"] == [], ev


def test_launched_with_placeholder_prod_rule_fails_closed(engine):
    ev = _ev(engine, _answered(engine, status="launched"), placeholders=["example-prod-service-placeholder"])
    assert ev["blocking"] and "__REPLACE_ME__" in " ".join(ev["errors"])
    # while preparing, the same placeholder is only advisory
    assert not _ev(engine, _answered(engine), placeholders=["x"])["blocking"]


@pytest.mark.parametrize("item,bad", [
    ("messaging-consent", {"status": "n/a"}),                                  # no reason
    ("messaging-consent", {"status": "n/a", "reason": "n/a"}),                 # placeholder reason
    ("accessibility", {"status": "done", "evidence": "yes"}),                  # too short
    ("accessibility", {"status": "done", "evidence": "TODO: run axe on every page later"}),
    ("accessibility", {"status": "done"}),                                     # no evidence
    ("spend-limits", {"status": "done", "evidence": GOOD_EVIDENCE, "evidence_files": ["netlify.toml"]}),
    ("spend-limits", {"status": "done", "evidence": GOOD_EVIDENCE, "evidence_files": ["../outside.txt"]}),
    ("spend-limits", {"status": "done", "evidence": GOOD_EVIDENCE, "evidence_files": ["/etc/hosts"]}),
    ("spend-limits", {"status": "done", "evidence": GOOD_EVIDENCE, "evidence_files": "netlify.toml"}),
    ("security-audit", {"status": "skipped"}),                                 # unknown state
    ("security-audit", "done"),                                                # not an object
])
def test_an_item_is_answered_only_with_evidence_or_a_reason(engine, item, bad):
    doc = _answered(engine, status="launched")
    doc["items"][item] = bad
    ev = _ev(engine, doc)
    assert item in ev["invalid"] and ev["blocking"], ev


def test_real_sentences_are_not_mistaken_for_placeholders(engine):
    doc = _answered(engine, status="launched")
    doc["items"]["accessibility"] = {"status": "done",
                                     "evidence": "Done: axe scan on 12 pages, 0 violations; keyboard pass ok."}
    doc["items"]["messaging-consent"] = {"status": "n/a",
                                         "reason": "None of the features send SMS, email or calls."}
    ev = _ev(engine, doc)
    assert not ev["blocking"] and ev["invalid"] == [], ev
    for short in ("yes", "done", "n/a", "ok", "none"):
        doc["items"]["messaging-consent"] = {"status": "n/a", "reason": short}
        assert "messaging-consent" in _ev(engine, doc)["invalid"], short


def test_evidence_files_must_exist_in_the_same_tree(engine):
    doc = _answered(engine, status="launched")
    doc["items"]["spend-limits"]["evidence_files"] = ["netlify.toml"]
    assert _ev(engine, doc, exists=lambda rel: rel == "netlify.toml")["blocking"] is False
    assert _ev(engine, doc, exists=lambda rel: False)["blocking"] is True


def test_a_missing_item_is_never_skipped(engine):
    doc = _answered(engine, status="launched")
    del doc["items"]["public-key-data-access"]
    ev = _ev(engine, doc)
    assert "public-key-data-access" in ev["invalid"] and ev["blocking"]


@pytest.mark.parametrize("text", [
    "{not json",
    "[]",
    json.dumps({"format": "tess-launch-readiness/1", "status": "live", "items": {}}),
    json.dumps({"format": "other/1", "status": "launched", "items": {}}),
])
def test_an_unreadable_record_fails_closed(engine, text):
    assert _ev(engine, text)["blocking"]


def test_unknown_item_is_an_error_and_blocks_once_launched(engine):
    doc = _answered(engine, status="launched")
    doc["items"]["vibes"] = {"status": "done", "evidence": GOOD_EVIDENCE}
    assert _ev(engine, doc)["blocking"]
    doc["status"] = "preparing"
    ev = _ev(engine, doc)
    assert ev["errors"] and not ev["blocking"]


def test_data_rules_in_tree_make_an_na_data_item_advisory(engine):
    doc = _answered(engine)
    doc["items"]["public-key-data-access"] = {"status": "n/a", "reason": "We do not store any user data."}
    ev = _ev(engine, doc, exists=lambda rel: rel == "supabase")
    assert any("supabase" in a for a in ev["advisories"]) and not ev["blocking"]


def test_placeholder_detection_reads_rules_not_hard_floors(engine):
    pol = {"policy": {"rules": [{"id": "a", "globs": ["src/**"]},
                                {"id": "b", "globs": ["__REPLACE_ME__/prod/**"]}],
                      "hard_floor_rules": [{"id": "c", "globs": ["__REPLACE_ME__/payments/**"]}]}}
    assert engine._launch_policy_placeholders(pol) == ["b"]
    shipped, errors = engine._gate_load_policy(REPO)
    assert not errors and engine._launch_policy_placeholders(shipped) == ["example-prod-service-placeholder"]


# ── the CLI and doctor (a create-tess-shaped instance) ───────────────────


@pytest.fixture(scope="module")
def inst(tmp_path_factory):
    root = h.full_instance(tmp_path_factory.mktemp("launch"))
    r = _tessctl(root, "render")
    assert r.returncode == 0, r.stdout + r.stderr
    return root


def _write(root: Path, doc) -> None:
    (root / "launch-readiness.json").write_text(doc if isinstance(doc, str) else json.dumps(doc, indent=2))


def test_doctor_warns_while_the_prod_rule_is_the_placeholder(inst):
    r = _tessctl(inst, "doctor")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "WARNING" in r.stdout and "example-prod-service-placeholder" in r.stdout
    assert "docs/LAUNCH_READINESS.md" in r.stdout


def test_doctor_quiet_once_the_prod_rule_names_real_paths(engine, tmp_path):
    root = tmp_path / "p"
    for rel in ("core/policy/policy.yaml",):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, root / rel)
    shutil.copytree(REPO / "core/contracts", root / "core/contracts")
    errs, warns = engine._launch_doctor_findings(root)
    assert errs == [] and any("__REPLACE_ME__" in w for w in warns)
    pol = root / "core/policy/policy.yaml"
    pol.write_text(pol.read_text().replace('"__REPLACE_ME__/prod/**"', '"src/**"'))
    assert engine._launch_doctor_findings(root) == ([], [])


def test_launch_cli_end_to_end(inst):
    path = inst / "launch-readiness.json"
    path.unlink(missing_ok=True)
    try:
        r = _tessctl(inst, "launch", "check")
        assert r.returncode == 0 and "launch init" in r.stdout
        r = _tessctl(inst, "launch", "init")
        assert r.returncode == 0 and path.is_file(), r.stdout + r.stderr
        assert _tessctl(inst, "launch", "init").returncode != 0          # never overwrites
        r = _tessctl(inst, "launch", "check")
        assert r.returncode == 0 and "NOT READY" in r.stdout and r.stdout.count("OPEN") == 6
        # doctor: a warning while preparing, never a failure
        d = _tessctl(inst, "doctor")
        assert d.returncode == 0 and "6 of 6 launch check(s) still unanswered" in d.stdout
        # mark-launched refused while items are open; nothing changes
        before = path.read_bytes()
        r = _tessctl(inst, "launch", "mark-launched")
        assert r.returncode == 1 and "REFUSED" in r.stdout and path.read_bytes() == before
        # every item answered, but the prod rule is still the placeholder: still refused
        doc = json.loads(before)
        for iid in doc["items"]:
            doc["items"][iid] = {"status": "done", "evidence": GOOD_EVIDENCE}
        _write(inst, doc)
        r = _tessctl(inst, "launch", "mark-launched")
        assert r.returncode == 1 and "__REPLACE_ME__" in r.stdout
        assert json.loads(path.read_text())["status"] == "preparing"
        # a hand-set "launched" with the placeholder fails check, doctor and doctor --json
        doc["status"] = "launched"
        _write(inst, doc)
        r = _tessctl(inst, "launch", "check")
        assert r.returncode == 1 and "FAIL" in r.stdout
        d = _tessctl(inst, "doctor")
        assert d.returncode == 1 and "LAUNCH READINESS" in d.stdout
        j = _tessctl(inst, "doctor", "--json")
        assert j.returncode == 1 and any(row.get("lock_status") == "launch-readiness"
                                         for row in json.loads(j.stdout))
        # an item reopened under "launched": same failure
        doc["items"]["accessibility"] = {"status": "open"}
        _write(inst, doc)
        assert _tessctl(inst, "launch", "check").returncode == 1
        c = json.loads(_tessctl(inst, "launch", "check", "--json").stdout)
        assert c["blocking"] and "accessibility" in c["open"]
    finally:
        path.unlink(missing_ok=True)


def test_mark_launched_succeeds_only_when_everything_is_answered(engine, tmp_path, monkeypatch, capsys):
    root = tmp_path / "p"
    (root / "core/policy").mkdir(parents=True)
    shutil.copytree(REPO / "core/contracts", root / "core/contracts")
    pol = (REPO / "core/policy/policy.yaml").read_text().replace('"__REPLACE_ME__/prod/**"', '"src/**"')
    (root / "core/policy/policy.yaml").write_text(pol)
    doc = engine._launch_template()
    for iid in doc["items"]:
        doc["items"][iid] = {"status": "done", "evidence": GOOD_EVIDENCE}
    _write(root, doc)
    args = type("A", (), {"launch_sub": "mark-launched"})()
    engine.cmd_launch(args, root)
    assert json.loads((root / "launch-readiness.json").read_text())["status"] == "launched"
    assert "now says launched" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        engine.cmd_launch(type("A", (), {"launch_sub": "check", "json_out": False})(), root)
    assert e.value.code == 0


def test_a_symlinked_record_fails_closed(engine, tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    (root / "elsewhere.json").write_text(json.dumps(_answered(engine)))
    os.symlink("elsewhere.json", root / "launch-readiness.json")
    ev = engine._launch_evaluate_worktree(root, policy_instance={"policy": {"rules": []}})
    assert ev["blocking"]


# ── the ship gate ─────────────────────────────────────────────────────────


def _gate_repo(tmp_path: Path, placeholder: bool = False) -> Path:
    root = tmp_path / "g"
    (root / "core/policy").mkdir(parents=True)
    shutil.copytree(REPO / "core/contracts", root / "core/contracts")
    pol = (REPO / "core/policy/policy.yaml").read_text()
    if not placeholder:
        pol = pol.replace('"__REPLACE_ME__/prod/**"', '"src/**"')
    (root / "core/policy/policy.yaml").write_text(pol)
    (root / "README.md").write_text("x\n")
    _git(tmp_path, "init", "-q", "-b", "main", str(root))
    _commit(root, "init", "core", "README.md")
    return root


def _ship(engine, root: Path, base: str, head: str) -> dict:
    changed = _git(root, "diff", "--name-only", base, head).splitlines()
    return engine._gate_run_ship_check(root, changed, None, [head], [base], emit_receipts=False)


def test_gate_refuses_a_launched_record_with_open_items(engine, tmp_path):
    root = _gate_repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    doc = engine._launch_template()
    doc["status"] = "launched"
    _write(root, doc)
    head = _commit(root, "launch", "launch-readiness.json")
    res = _ship(engine, root, base, head)
    assert res["blocked"], res
    safe = engine._safe_gate_result(res, phase="ci")
    assert any(r.startswith("LAUNCH_READINESS_INCOMPLETE:") for r in safe["reasons"]), safe
    assert not any("INTERNAL_ERROR_REDACTED" in r for r in safe["reasons"])
    assert "accessibility" not in json.dumps(safe)          # no item names in the public projection


def test_gate_passes_preparing_and_complete_records(engine, tmp_path):
    root = _gate_repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    _write(root, engine._launch_template())
    head = _commit(root, "prep", "launch-readiness.json")
    assert not _ship(engine, root, base, head)["blocked"]
    _write(root, _answered(engine, status="launched"))
    head2 = _commit(root, "launched", "launch-readiness.json")
    assert not _ship(engine, root, head, head2)["blocked"]


def test_gate_refuses_launched_while_prod_rule_is_placeholder(engine, tmp_path):
    root = _gate_repo(tmp_path, placeholder=True)
    base = _git(root, "rev-parse", "HEAD")
    _write(root, _answered(engine, status="launched"))
    head = _commit(root, "launched", "launch-readiness.json")
    res = _ship(engine, root, base, head)
    assert res["blocked"] and any("LAUNCH_READINESS_INCOMPLETE" in r for r in res["reasons"])


def test_gate_reads_the_pushed_commit_not_the_working_tree(engine, tmp_path):
    root = _gate_repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    bad = engine._launch_template()
    bad["status"] = "launched"
    _write(root, bad)
    head = _commit(root, "bad", "launch-readiness.json")
    _write(root, _answered(engine, status="launched"))     # fixed only on disk, not committed
    assert _ship(engine, root, base, head)["blocked"]
    # and the reverse: a good commit is not blocked by a broken working copy
    head2 = _commit(root, "good", "launch-readiness.json")
    _write(root, "{broken")
    assert not _ship(engine, root, head, head2)["blocked"]


def test_gate_evidence_file_must_be_in_the_pushed_commit(engine, tmp_path):
    root = _gate_repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    doc = _answered(engine, status="launched")
    doc["items"]["accessibility"]["evidence_files"] = ["qa/axe-report.json"]
    _write(root, doc)
    (root / "qa").mkdir()
    (root / "qa/axe-report.json").write_text("{}")          # on disk, never committed
    head = _commit(root, "launched", "launch-readiness.json")
    assert _ship(engine, root, base, head)["blocked"]
    head2 = _commit(root, "report", "qa/axe-report.json")
    assert not _ship(engine, root, head, head2)["blocked"]


def test_gate_ci_cli_explains_the_refusal_without_naming_items(inst):
    path = inst / "launch-readiness.json"
    _git(inst, "-c", "user.email=t@tess.test", "-c", "user.name=T", "-c", "commit.gpgsign=false",
         "commit", "-q", "--no-verify", "--allow-empty", "-m", "base")
    base = _git(inst, "rev-parse", "HEAD")
    try:
        doc = json.loads(json.dumps({"format": "tess-launch-readiness/1", "status": "launched", "items": {}}))
        _write(inst, doc)
        head = _commit(inst, "launch", "launch-readiness.json")
        r = _tessctl(inst, "gate", "ci", "--base", base, "--head", head)
        assert r.returncode == 1, r.stdout + r.stderr
        assert "LAUNCH_READINESS_INCOMPLETE" in r.stdout and "tessctl launch check" in r.stdout
        assert "spend-limits" not in r.stdout and "accessibility" not in r.stdout
    finally:
        _git(inst, "reset", "-q", base)
        path.unlink(missing_ok=True)


def test_gate_refuses_deleting_a_launched_record(engine, tmp_path):
    root = _gate_repo(tmp_path)
    _write(root, _answered(engine, status="launched"))
    base = _commit(root, "launched", "launch-readiness.json")
    _git(root, "rm", "-q", "launch-readiness.json")
    _git(root, "-c", "user.email=t@tess.test", "-c", "user.name=T", "-c", "commit.gpgsign=false",
         "commit", "-q", "--no-verify", "-m", "drop")
    head = _git(root, "rev-parse", "HEAD")
    res = _ship(engine, root, base, head)
    assert res["blocked"] and any("deletes it" in r for r in res["reasons"]), res
    # stepping back explicitly is allowed
    _git(root, "reset", "-q", "--hard", base)
    doc = _answered(engine, status="preparing")
    _write(root, doc)
    head2 = _commit(root, "step back", "launch-readiness.json")
    assert not _ship(engine, root, base, head2)["blocked"]


def test_gate_symlinked_record_in_a_commit_fails_closed(engine, tmp_path):
    root = _gate_repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    (root / "real.json").write_text(json.dumps(_answered(engine, status="launched")))
    os.symlink("real.json", root / "launch-readiness.json")
    head = _commit(root, "link", "real.json", "launch-readiness.json")
    assert _ship(engine, root, base, head)["blocked"]


# ── doctrine: routed to the verifier, and in step with the engine ────────


def test_doctrine_routes_launches_and_makes_the_audit_standard(engine):
    vr = (REPO / "conductor/verification-routing.md").read_text()
    assert "## Launch Readiness" in vr and "## Security Audit Is a Standard Step" in vr
    assert "Externally visible launch" in vr and "playbooks/launch-readiness.md" in vr
    assert "tessctl audit validate" in vr and "security-tier" in vr
    rp = (REPO / "conductor/release-process.md").read_text()
    assert "### Security audit for security-tier changes" in rp and "tessctl launch" in rp
    pb = (REPO / "conductor/playbooks/launch-readiness.md").read_text()
    doc = (REPO / "docs/LAUNCH_READINESS.md").read_text()
    for iid in engine.LAUNCH_ITEM_IDS:   # the doctrine, the doc and the engine list the same items
        assert f"`{iid}`" in vr and f"`{iid}`" in pb and f"`{iid}`" in doc, iid
    readme = (REPO / "conductor/playbooks/README.md").read_text()
    n = len([p for p in (REPO / "conductor/playbooks").glob("*.md") if p.name != "README.md"])
    assert f"**Documented playbook files: {n}.**" in readme and "launch-readiness.md" in readme
    for rel in ("conductor/verification-routing.md", "conductor/release-process.md",
                "conductor/playbooks/launch-readiness.md", "conductor/playbooks/README.md"):
        assert (REPO / rel).read_bytes() == (REPO / ".tess/core" / rel).read_bytes(), rel
