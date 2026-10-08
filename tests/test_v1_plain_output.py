"""v1.0 "B4" first-run findings: plain output a non-technical person can act on.

- `tessctl help` / `tessctl --version` work (they used to be argparse errors);
- `doctor` and `update` print a short summary by default, the full listing
  with --verbose, and their exit codes do not change;
- onboarding never says "complete" after a failed apply, and says the fix;
- the shipped docs never tell anyone to skip the safety checks, never name
  skills that do not ship, and list only the runtimes that are supported.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import _brain_oobe_helpers as h

REPO = Path(__file__).resolve().parent.parent
ENGINE = REPO / ".tess" / "bin" / "tessctl"


def _quiet_env(root: Path) -> dict:
    env = {**os.environ, "TESS_ROOT": str(root)}
    env.pop("TESS_VERBOSE", None)
    return env


def _tessctl(root: Path, *args: str, verbose_env: bool = False) -> subprocess.CompletedProcess:
    env = _quiet_env(root)
    # hermetic: no Codex user config, so doctor's Codex hook-trust warning
    # (tests/test_v1_r2_ux_fixes.py) never depends on this machine's ~/.codex
    env["CODEX_HOME"] = str(root / ".no-codex-home")
    if verbose_env:
        env["TESS_VERBOSE"] = "1"
    return subprocess.run([sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
                          cwd=str(root), env=env, capture_output=True, text=True)


def _rendered_instance(tmp: Path) -> Path:
    root = h.full_instance(tmp)
    r = _tessctl(root, "render")
    assert r.returncode == 0, r.stdout + r.stderr
    return root


@pytest.fixture(scope="module")
def instance(tmp_path_factory):
    return _rendered_instance(tmp_path_factory.mktemp("b4"))


# ── help and --version ────────────────────────────────────────────────────


def test_help_and_version_work_without_errors(instance):
    for args in (("help",), ("--help",)):
        r = _tessctl(instance, *args)
        assert r.returncode == 0, r.stderr
        assert "doctor" in r.stdout and "update" in r.stdout and "error" not in r.stderr
    r = _tessctl(instance, "help", "doctor")
    assert r.returncode == 0 and "--verbose" in r.stdout and "usage: tessctl doctor" in r.stdout
    lock_version = re.search(r"^  version: (\S+)$", (instance / ".tess" / "tess.lock").read_text(), re.M).group(1)
    r = _tessctl(instance, "--version")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "tessctl %s (Tess OS)" % lock_version
    # Outside any Tess OS folder: still exit 0, with a plain explanation.
    outside = subprocess.run([sys.executable, str(ENGINE), "--version"], cwd="/",
                             env={k: v for k, v in os.environ.items() if k != "TESS_ROOT"},
                             capture_output=True, text=True)
    assert outside.returncode == 0 and outside.stdout.startswith("tessctl ")


# ── doctor: short by default ──────────────────────────────────────────────


def test_doctor_default_is_one_plain_summary(instance):
    r = _tessctl(instance, "doctor")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert re.fullmatch(r"All good — [\d,]+ files checked, nothing changed\.", lines[-2]), r.stdout
    assert lines[-1] == "doctor: OK"
    assert len(lines) <= 3, "default doctor output must be a short summary:\n" + r.stdout
    assert "  ok  " not in r.stdout and "pristine:" not in r.stdout


def test_doctor_verbose_and_env_keep_the_full_listing(instance):
    for r in (_tessctl(instance, "doctor", "--verbose"), _tessctl(instance, "doctor", verbose_env=True)):
        assert r.returncode == 0
        assert "  ok          .tess/core/MANIFEST.md" in r.stdout
        assert "uncaptured drift: 0" in r.stdout and r.stdout.rstrip().endswith("doctor: OK")
    j = _tessctl(instance, "doctor", "--json")
    assert j.returncode == 0 and isinstance(json.loads(j.stdout), list)


def test_doctor_default_still_shows_problems_and_exit_code(tmp_path):
    root = _rendered_instance(tmp_path)
    target = root / ".claude" / "agents" / "ada.md"
    target.write_text(target.read_text() + "\nhand edit\n")
    quiet = _tessctl(root, "doctor")
    loud = _tessctl(root, "doctor", "--verbose")
    assert quiet.returncode == loud.returncode == 1
    assert "DRIFT       .claude/agents/ada.md" in quiet.stdout
    assert "doctor: FAIL" in quiet.stdout and "`tessctl doctor --verbose` lists every file" in quiet.stdout
    assert "All good" not in quiet.stdout and "  ok  " not in quiet.stdout


# ── update: short by default ──────────────────────────────────────────────


def test_update_summary_counts_and_keeps_warnings(engine, capsys):
    text = "\n".join([
        "tessctl update — current: v2 v0.2.0",
        "", "Step 0: snapshot …", "  snapshot → .tess/snapshots/x",
        "Step 5-6: plan and apply …",
        "  [fast-forward] a.md  — core-managed → fast-forward from staging",
        "  [fast-forward] b.md  — core-managed → fast-forward from staging",
        "  [merge       ] c.md  — locally-modified + upstream changed → 3-way merge",
        "  WARN  skipped 'd.md' (gate): refused",
        "  A3: version bumped → 1.0.0 (upstream_ref: v1.0.0)",
        "", "update: complete",
    ])
    engine._print_update_summary(text)
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "tessctl update — you have Tess OS v0.2.0"
    assert "  WARN  skipped 'd.md' (gate): refused" in out
    assert "Of Tess's own files, 2 updated, 1 merged with your changes." in out
    assert "update: complete" in out and "A3: version bumped → 1.0.0 (upstream_ref: v1.0.0)" in out
    assert not any(l.startswith("Step ") or "[fast-forward]" in l for l in out)


def test_update_failure_prints_everything(engine, capsys):
    def boom():
        print("Step 4: fetch …")
        print("  detail a helper needs")
        sys.exit(1)

    with pytest.raises(SystemExit) as exc:
        engine._run_summarised(boom, lambda text: print("SUMMARY"))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "detail a helper needs" in out and "SUMMARY" not in out


def test_update_verbose_flag_is_accepted(engine):
    args = engine.build_parser().parse_args(["update", "--verbose", "--check"])
    assert args.verbose is True and args.check is True


# ── onboarding status honesty ─────────────────────────────────────────────


def test_failed_apply_never_reports_complete(tmp_path):
    root = h.mini_instance(tmp_path)
    init = h.onboard(root, "init", "--non-interactive", "--answers",
                     str(h.FIXTURES / "answers-personal.json"))
    assert init.returncode == 0, init.stdout + init.stderr
    hook = root / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'blocked by a test hook' >&2\nexit 1\n")
    hook.chmod(0o755)

    failed = h.onboard(root, "apply")
    assert failed.returncode != 0, failed.stdout
    onb = json.loads((root / "brain" / "brain.json").read_text())["onboarding"]
    assert onb["status"] == "in_progress" and onb["completed_at"] is None
    assert onb["last_apply_error"]

    st = json.loads(h.onboard(root, "status", "--json").stdout)
    assert st["status"] == "in_progress" and st["fix"] == "python3 scripts/brain/onboard.py apply"
    human = h.onboard(root, "status").stdout
    assert "complete" not in human.replace("did not finish", "")
    assert "setup did not finish" in human and "python3 scripts/brain/onboard.py apply" in human

    hook.unlink()
    again = h.onboard(root, "apply")
    assert again.returncode == 0, again.stdout + again.stderr
    onb = json.loads((root / "brain" / "brain.json").read_text())["onboarding"]
    assert onb["status"] == "complete" and "last_apply_error" not in onb
    assert h.git(root, "status", "--porcelain").stdout == ""


# ── docs ──────────────────────────────────────────────────────────────────


def _shipped_markdown() -> list:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others",
                          "--exclude-standard", "*.md", "*.tpl"], capture_output=True, check=True).stdout
    skip = ("gate-arena/", "tests/", "create-tess/template/", "kb/", "CHANGELOG.md", "docs/superpowers/")
    return [f for f in out.decode().split("\0") if f and not f.startswith(skip) and (REPO / f).is_file()]


def test_no_doc_tells_anyone_to_use_no_verify():
    command_line = re.compile(r"^\s*(\$\s*)?git\s+(push|commit)\b[^\n]*--no-verify")
    offenders = []
    for rel in _shipped_markdown():
        for n, line in enumerate((REPO / rel).read_text(encoding="utf-8").splitlines(), 1):
            if command_line.search(line):
                offenders.append("%s:%d" % (rel, n))
    assert offenders == [], "a doc gives a --no-verify command: %s" % offenders
    user_facing = ["README.md", "docs/TECHNICAL_OVERVIEW.md", "docs/STATUS.md",
                   "docs/brain/ONBOARDING.md", "docs/brain/SECOND_BRAIN.md",
                   ".claude/skills/brain-onboard/SKILL.md", ".agents/skills/brain-onboard/SKILL.md",
                   "scripts/brain/oobe/apply.py"]
    for rel in user_facing:
        assert "--no-verify" not in (REPO / rel).read_text(encoding="utf-8"), rel


def test_docs_name_no_skill_that_does_not_ship():
    shipped = {p.parent.name for p in (REPO / ".claude" / "skills").glob("*/SKILL.md")}
    for missing in ("brain-decide", "brain-remember", "brain-save"):
        if missing in shipped:
            continue
        hits = [rel for rel in _shipped_markdown() + ["scripts/brain/onboard.py"]
                if missing in (REPO / rel).read_text(encoding="utf-8")]
        assert hits == [], "%s is referenced but does not ship: %s" % (missing, hits)


def test_onboarding_runtime_list_matches_support():
    text = (REPO / "docs" / "brain" / "ONBOARDING.md").read_text(encoding="utf-8")
    assert "kimi" not in text.lower()
    assert "Claude Code" in text and "Codex" in text
    assert "| Gemini CLI (advisory) |" in text


def test_readme_leads_with_plain_quickstart():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    for stale in ("describes v0.2.0", "npm serves", "npm served", "1,033", "1033 files", "#181", "deferred"):
        assert stale not in text, stale
    for need in ("## What you need", "Node.js 18", "git", "Python 3.9", "macOS already has it",
                 "Claude Code", "Codex", "npm create tess@latest my-os",
                 "open the folder `my-os` in Claude Code or Codex and say hi", "SECURITY.md"):
        assert need.lower() in " ".join(text.split()).lower(), need
    assert text.index("## What you need") < text.index("## Quickstart") < text.index("## More detail")
    status = (REPO / "docs" / "STATUS.md").read_text(encoding="utf-8")
    assert "## v1.0.0 trust facts" in status and "deferred to v0.2.1" not in status
