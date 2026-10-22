"""v1.0.0: Cloudflare's security-audit skill ships in both runtimes, unmodified.

Pins:
  * every upstream file in `.tess/core/skills/security-audit/` has exactly the
    bytes of upstream commit c1c8a8c (hash list in UPSTREAM.md, and the digest
    of that list held HERE, so a file and its record cannot drift together);
  * the skill renders to `.claude/skills/security-audit/` (lock entries) and
    `.agents/skills/security-audit/` (codex target) byte for byte, with
    LICENSE, UPSTREAM.md and TESS.md present;
  * only this one skill folder is owned under `.agents/` (user skills stay
    unreachable to the write gate);
  * the upstream validator test suites pass under node (hard failure in CI);
  * `tessctl audit validate <run-dir>` passes a valid run, fails an invalid or
    empty one, and fails closed with a plain message when node is missing;
  * node runs with a scratch HOME and TMPDIR, never the operator's own.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

UPSTREAM_COMMIT = "c1c8a8c1471069fb0e188eeaff69b8e8db6564a8"
# sha256 of the hash block in UPSTREAM.md (the lines between the markers,
# inside the code fence, each ending in "\n"). Update only together with a
# reviewed upstream update (UPSTREAM.md "How to update").
UPSTREAM_LIST_SHA256 = "cad300547caef7396115424fb61251bb03d397b16ff0243ceed0b5e12d8368f4"

SKILL = "security-audit"
CORE = REPO_ROOT / ".tess" / "core" / "skills" / SKILL
CLAUDE_LIVE = REPO_ROOT / ".claude" / "skills" / SKILL
AGENTS_LIVE = REPO_ROOT / ".agents" / "skills" / SKILL
TESS_FILES = {"UPSTREAM.md", "TESS.md"}
NODE = shutil.which("node")
IN_CI = bool(os.environ.get("CI"))


def _upstream_list() -> tuple[str, dict]:
    text = (CORE / "UPSTREAM.md").read_text(encoding="utf-8")
    m = re.search(r"<!-- upstream-sha256:begin -->\n```\n(.*?)```\n<!-- upstream-sha256:end -->",
                  text, re.S)
    assert m, "UPSTREAM.md lost its upstream-sha256 block"
    block = m.group(1)
    entries = {}
    for line in block.splitlines():
        digest, name = line.split("  ", 1)
        entries[name] = digest
    return block, entries


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_node():
    if NODE:
        return NODE
    if IN_CI:
        pytest.fail("node is required in CI to run the security-audit validator tests")
    pytest.skip("node not installed (required in CI)")


def test_upstream_record_is_pinned_here():
    block, entries = _upstream_list()
    assert hashlib.sha256(block.encode("utf-8")).hexdigest() == UPSTREAM_LIST_SHA256
    assert UPSTREAM_COMMIT in (CORE / "UPSTREAM.md").read_text(encoding="utf-8")
    assert len(entries) == 21 and "SKILL.md" in entries and "LICENSE" in entries


@pytest.mark.parametrize("where", [CORE, CLAUDE_LIVE, AGENTS_LIVE],
                         ids=["core", "claude", "codex"])
def test_every_runtime_copy_is_upstream_bytes(where):
    _block, entries = _upstream_list()
    assert where.is_dir(), f"{where} missing"
    present = {p.name for p in where.iterdir()}
    assert present == set(entries) | TESS_FILES, sorted(present ^ (set(entries) | TESS_FILES))
    for name, digest in entries.items():
        assert not (where / name).is_symlink()
        assert _sha(where / name) == digest, f"{where.name}/{name} differs from upstream {UPSTREAM_COMMIT[:7]}"
    for name in TESS_FILES:
        assert (where / name).read_bytes() == (CORE / name).read_bytes()


def test_license_is_cloudflare_mit_and_named_in_notice():
    lic = (CORE / "LICENSE").read_text(encoding="utf-8")
    assert lic.startswith("MIT License\n\nCopyright (c) 2025-2026 Cloudflare, Inc.\n")
    assert "THE SOFTWARE IS PROVIDED \"AS IS\"" in lic
    notice = (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "security-audit" in notice and "Cloudflare, Inc." in notice
    assert "github.com/cloudflare/security-audit-skill" in notice


def test_skill_frontmatter_is_loadable_in_both_runtimes():
    text = (AGENTS_LIVE / "SKILL.md").read_text(encoding="utf-8")
    head = text.split("---")[1]
    assert re.search(r"^name: security-audit$", head, re.M)  # == directory name
    desc = re.search(r"^description: (.+)$", head, re.M).group(1)
    assert 0 < len(desc) <= 1024 and "security audit" in desc.lower()


def test_claude_copies_are_lock_pinned(engine):
    lock = engine.load_lock(REPO_ROOT)
    for path in sorted(CORE.iterdir()):
        key = f".tess/core/skills/{SKILL}/{path.name}"
        attrs = lock["files"].get(key)
        assert attrs, f"{key} has no tess.lock entry"
        assert attrs["status"] == "core-managed"
        assert attrs["live_path"] == f".claude/skills/{SKILL}/{path.name}"
        assert attrs["base_sha"] == "sha256:" + _sha(path)


def test_codex_target_renders_exact_core_bytes(engine):
    codex = engine.RENDER_TARGETS["codex"]
    generated = codex.render_generated_paths(REPO_ROOT)
    for path in sorted(CORE.iterdir()):
        rel = f".agents/skills/{SKILL}/{path.name}"
        assert rel in generated
        assert codex.expected_live_bytes(REPO_ROOT, rel) == path.read_bytes()
    assert f".agents/skills/{SKILL}/**" in codex.live_globs()


def test_only_this_skill_folder_is_owned_under_agents(engine):
    manifest = json.loads((REPO_ROOT / "tess.manifest.json").read_text(encoding="utf-8"))
    owned, never = manifest["owned_globs"], manifest["never_touch"]
    assert f".agents/skills/{SKILL}/**" in owned
    assert engine.path_matches_globs(f".agents/skills/{SKILL}/SKILL.md", owned)
    assert not engine.path_matches_globs(".agents/skills/my-own-skill/SKILL.md", owned)
    assert not engine.path_matches_globs(".agents/skills/security-audit-evil/SKILL.md", owned)
    assert engine.path_matches_globs(".agents/skills/my-own-skill/SKILL.md", never)


def test_render_into_a_fresh_project_writes_the_skill(project, run_cli):
    """A synthetic codex-only install: render copies the core skill byte for
    byte into .agents/skills/security-audit/ and a second render changes nothing."""
    tpl = ".tess/core/templates/agents-md/AGENTS.md.tpl"
    project.add(None, "# AGENTS.md Fixture\n", core_key=tpl, render_live=False)
    project.add(None, 'approval_policy = "on-request"\n',
                core_key=".tess/core/templates/agents-md/codex-config.toml.tpl", render_live=False)
    for path in sorted(CORE.iterdir()):
        project.add(f".claude/skills/{SKILL}/{path.name}", path.read_text(encoding="utf-8"),
                    core_key=f".tess/core/skills/{SKILL}/{path.name}", render_live=True)
    project.write()
    mf = project.root / "tess.manifest.json"
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    manifest["render_targets"]["enabled"] = ["codex"]
    mf.write_text(json.dumps(manifest), encoding="utf-8")

    r = run_cli(project.root, "render", "--target", "codex")
    assert r.returncode == 0, r.stdout + r.stderr
    out = project.root / ".agents" / "skills" / SKILL
    for path in sorted(CORE.iterdir()):
        assert (out / path.name).read_bytes() == path.read_bytes(), path.name
    first = {p.name: p.read_bytes() for p in out.iterdir()}
    r2 = run_cli(project.root, "render", "--target", "codex")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert {p.name: p.read_bytes() for p in out.iterdir()} == first


# ---------------------------------------------------------------------------
# node: the upstream suites and `tessctl audit validate`
# ---------------------------------------------------------------------------

def _scratch_env(tmp_path: Path, path_value: str | None = None) -> dict:
    home = tmp_path / "home"
    tmp = tmp_path / "tmp"
    home.mkdir(exist_ok=True)
    tmp.mkdir(exist_ok=True)
    return {"PATH": path_value if path_value is not None else os.environ.get("PATH", ""),
            "HOME": str(home), "TMPDIR": str(tmp), "NO_COLOR": "1"}


@pytest.mark.parametrize("suite", ["validate-findings.test.cjs", "validate-coverage-ledger.test.cjs"])
def test_upstream_validator_suites_pass(suite, tmp_path):
    node = _require_node()
    r = subprocess.run([node, str(CORE / suite)], cwd=str(tmp_path), env=_scratch_env(tmp_path),
                       capture_output=True, text=True, timeout=300)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-4000:]
    passed = re.search(r"^(?:#|ℹ) pass (\d+)$", out, re.M)
    failed = re.search(r"^(?:#|ℹ) fail (\d+)$", out, re.M)
    assert passed and int(passed.group(1)) > 0, out[-2000:]
    assert failed and int(failed.group(1)) == 0, out[-2000:]


def _valid_unit(node: str, tmp_path: Path) -> dict:
    refs = {"surface": "src/router.ts#POST /users/:id", "boundary": "src/authz.ts#requireOwner",
            "subsystem": "packages/api", "attack_class": "ATTACK-CLASSES.md#Access control"}
    script = ("const v=require(process.argv[1]);"
              "process.stdout.write(v.canonicalCoverageId(JSON.parse(process.argv[2])))")
    cid = subprocess.run([node, "-e", script, str(CORE / "validate-coverage-ledger.cjs"),
                          json.dumps(refs)], env=_scratch_env(tmp_path), capture_output=True,
                         text=True, timeout=60, check=True).stdout
    return {
        "coverage_id": cid, "canonical_refs": refs, "surface": "Update-user route",
        "boundary": "Object ownership", "subsystem": "API", "attack_class": "Access control",
        "starting_paths": ["src/router.ts", "src/authz.ts"],
        "ordinary_attack_class_block": "ATTACK-CLASSES.md#Access control",
        "selected_companion_blocks": [], "excluded_blocks": [], "prior_status": "none",
        "attempts": [], "wave": 1, "status": "planned", "agent_id": None, "reviewed_paths": [],
        "local_checks": [], "result_fingerprints": [], "unresolved": [],
    }


def _validate(tmp_path: Path, run: Path, path_value: str | None = None):
    return subprocess.run(
        [sys.executable, "-I", "-B", str(REPO_ROOT / ".tess" / "bin" / "tessctl"),
         "audit", "validate", str(run)],
        cwd=str(REPO_ROOT), env={**_scratch_env(tmp_path, path_value), "TESS_ROOT": str(REPO_ROOT)},
        capture_output=True, text=True, timeout=300)


def test_audit_validate_passes_a_valid_run(tmp_path):
    node = _require_node()
    run = tmp_path / "run-1"
    run.mkdir()
    (run / "findings.json").write_text("[]\n", encoding="utf-8")
    (run / "coverage-ledger.json").write_text(json.dumps([_valid_unit(node, tmp_path)]), encoding="utf-8")
    r = _validate(tmp_path, run)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK    findings.json" in r.stdout and "OK    coverage-ledger.json" in r.stdout
    assert "Audit run valid" in r.stdout


@pytest.mark.parametrize("case", ["bad-findings", "bad-ledger", "empty-ledger", "missing-file"])
def test_audit_validate_fails_an_invalid_run(case, tmp_path):
    node = _require_node()
    run = tmp_path / "run-1"
    run.mkdir()
    findings = {"x": 1} if case == "bad-findings" else []
    ledger = {"bad-ledger": [{"coverage_id": 1}], "empty-ledger": []}.get(
        case, [_valid_unit(node, tmp_path)])
    (run / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
    if case != "missing-file":
        (run / "coverage-ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    r = _validate(tmp_path, run)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "Audit run NOT valid" in r.stdout
    assert "Audit run valid" not in r.stdout


def test_audit_validate_fails_closed_without_node(tmp_path):
    run = tmp_path / "run-1"
    run.mkdir()
    (run / "findings.json").write_text("[]", encoding="utf-8")
    (run / "coverage-ledger.json").write_text("[]", encoding="utf-8")
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    r = _validate(tmp_path, run, path_value=str(empty_bin))
    assert r.returncode == 2, r.stdout + r.stderr
    assert "`node` was not found" in r.stderr and "Nothing was checked" in r.stderr
    assert "valid" not in r.stdout.lower()


def test_audit_validate_rejects_a_missing_folder(tmp_path):
    r = _validate(tmp_path, tmp_path / "nope")
    assert r.returncode != 0
    assert "is not a folder" in (r.stdout + r.stderr)
