"""`onboard.py apply`: turn the answered interview into a committed brain.

Create-if-absent and idempotent: a second apply changes nothing and leaves
`git status --porcelain` empty. Refuses (exit 3) when onboarding is not fully
answered or when run in the Tess OS source repo. Never pushes and never uses
--no-verify: the first push of a new instance is a documented operator step.
"""
from __future__ import annotations

import datetime as _dt
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import answers, chart, entities, gitignore, records, scaffold, state
from .slug import one_line, slugify

SEED_PUSH = ("First push of a new instance (run it yourself, once, after reading `git log`): "
             "git push --no-verify -u origin main")


def value(brain: Dict[str, Any], field: str, default: Any = None) -> Any:
    entry = answers.answered(brain).get(field)
    return entry.get("value", default) if entry else default


def build_ctx(brain: Dict[str, Any]) -> Dict[str, Any]:
    tz = brain.get("timezone") or "UTC"
    now = state.in_tz(_dt.datetime.now().astimezone(), tz)
    # The quarter follows the onboarding answer's time, so a scaffold is
    # reproducible from its answers (fixtures, a re-apply next quarter).
    started = state.parse_iso((answers.answered(brain).get("mode") or {}).get("at", ""))
    ref = state.in_tz(started, tz) if started else now
    ident = brain.get("identity") or {}
    principals = [p.get("name") or p.get("slug") for p in brain.get("principals", [])[1:]]
    presets = brain.get("presets") or []
    modes = brain.get("modes") or []
    quarter = "%d-Q%d" % (ref.year, (ref.month - 1) // 3 + 1)
    ctx = {
        "today": now.date().isoformat(), "quarter": quarter, "timezone": tz,
        "operator_name": ident.get("operator_name", ""), "operator_slug": ident.get("operator_slug", ""),
        "assistant_name": ident.get("assistant_name", "Tess"),
        "address_as": value(brain, "address_as") or ident.get("operator_name", ""),
        "modes_line": modes_line(modes), "presets_line": ", ".join(presets) or "none",
        "principals_line": ", ".join([ident.get("operator_name", "")] + principals),
        "agency_name": value(brain, "agency_name", "Agency") or "Agency",
        "agency_offer": one_line(value(brain, "agency_offer", "") or "(not stated yet)"),
        "org_name": value(brain, "org_name", "Organisation") or "Organisation",
        "operator_seat": slugify(value(brain, "operator_seat", "lead") or "lead"),
        "journal": (brain.get("capture") or {}).get("journal", "commit-redacted"),
    }
    return ctx


def modes_line(modes: List[str]) -> str:
    if not modes:
        return "none"
    return "%s (primary: %s)" % (", ".join(modes), modes[0])


def finalize_brain(brain: Dict[str, Any]) -> None:
    """Copy the answers into the brain.json v1 fields ws-learn reads."""
    ident = brain.setdefault("identity", {})
    ident["operator_name"] = value(brain, "operator_name", ident.get("operator_name", ""))
    ident["operator_slug"] = slugify(ident["operator_name"])
    ident["assistant_name"] = value(brain, "assistant_name", ident.get("assistant_name") or "Tess")
    brain["timezone"] = value(brain, "timezone", brain.get("timezone") or "UTC")
    answered_modes = list(value(brain, "mode", []) or [])
    modes = answered_modes + [m for m in brain.get("modes") or [] if m not in answered_modes]
    brain["modes"], brain["primary_mode"] = modes, modes[0]
    preset = value(brain, "preset")
    brain["presets"] = [preset] if preset else []
    brain["entity_roots"] = scaffold.entity_roots(modes)
    owner = {"slug": ident["operator_slug"], "name": ident["operator_name"], "role": "owner",
             "decides": True, "scope": ["**"], "aliases": [], "git_emails": [], "journal_consent": "shared"}
    brain["principals"] = [owner] + [_principal(p) for p in value(brain, "principals", []) or []]
    brain.setdefault("capture", {})["journal"] = value(brain, "journal", "commit-redacted")
    brain.setdefault("save", {})["autopush"] = bool(value(brain, "autopush", False))
    remote = brain.setdefault("remote", {"name": "origin", "visibility": "unknown", "verified_via": None})
    remote["url"] = value(brain, "remote_url")
    brain["runtimes"] = value(brain, "runtimes", brain.get("runtimes") or [])


def _principal(p: Dict[str, Any]) -> Dict[str, Any]:
    return {"slug": slugify(p["name"]), "name": p["name"], "role": p.get("role", "principal"),
            "decides": bool(p.get("decides", True)), "scope": p.get("scope") or ["**"],
            "aliases": [], "git_emails": [], "journal_consent": "unknown"}


def scaffold_modes(plan: scaffold.Plan, brain: Dict[str, Any], ctx: Dict[str, Any],
                   modes: List[str]) -> None:
    """Presets first (create-only, so their files win), then each mode base, then seeds."""
    for preset in brain.get("presets") or []:
        pm = scaffold.load_manifest("presets", preset)
        if pm.get("base_mode") in modes:
            for item in pm.get("templates", []):
                scaffold.materialize(plan, item["template"], item["dest"], ctx)
    for mode in modes:
        manifest = scaffold.load_manifest("modes", mode)
        entities.add_base(plan, manifest, ctx)
        for seed in manifest.get("seed", []):
            for name in (value(brain, seed["field"], []) or [])[: seed.get("max", 50)]:
                entities.add(plan, brain, ctx, seed["kind"], name, mode=mode, extra=_seed_extra(ctx, seed))
    seed_preset_kinds(plan, brain, ctx, modes)


def _seed_extra(ctx: Dict[str, Any], seed: Dict[str, Any]) -> Dict[str, Any]:
    return {"holder": "unfilled"} if seed["kind"] == "seat" else {}


def seed_preset_kinds(plan: scaffold.Plan, brain: Dict[str, Any], ctx: Dict[str, Any],
                      modes: List[str]) -> None:
    """Preset seats plus the operator's own seat (organisation mode)."""
    if "organisation" not in modes:
        return
    seats = [ctx["operator_seat"]]
    for preset in brain.get("presets") or []:
        seats.extend(scaffold.load_manifest("presets", preset).get("seats", []))
    for seat in seats:
        holder = ctx["operator_name"] if seat == ctx["operator_seat"] else "unfilled"
        entities.add(plan, brain, ctx, "seat", seat, mode="organisation", extra={"holder": holder})


# ------------------------------------------------------------------ git -----

def git(root: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, text=True,
                          check=check)


def commit_brain(root: Path, message: str, extra_paths: List[str]) -> Optional[str]:
    """Seed commit (repo with no commits) or a path-scoped brain commit.

    The installed gate pre-commit runs on both; nothing here bypasses it.
    Returns the new HEAD sha, or None when there was nothing to commit.
    """
    if git(root, "rev-parse", "--git-dir").returncode != 0:
        print("apply: not a git repository; skipped the commit (run `git init`, then apply again)")
        return None
    if git(root, "rev-parse", "--verify", "-q", "HEAD").returncode != 0:
        git(root, "add", "-A")
        return _commit(root, ["commit", "-q", "-m", "tess: seed instance + second brain (onboarding)"])
    paths = [p for p in ["brain", "memory/projects"] + extra_paths if (root / p).exists()]
    git(root, "add", "--", *paths)
    if git(root, "diff", "--cached", "--quiet", "--", *paths).returncode == 0:
        return None
    return _commit(root, ["commit", "-q", "-m", message, "--"] + paths)


def _commit(root: Path, args: List[str]) -> str:
    done = git(root, *args)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()[-12:]
        raise state.BrainError("git commit failed (the brain files are written; fix and re-run apply):\n  "
                               + "\n  ".join(detail), 4)
    return git(root, "rev-parse", "--short", "HEAD").stdout.strip()


def sync_identity(root: Path, brain: Dict[str, Any], seed: bool) -> None:
    """Make operator/profile.json (and so the rendered CLAUDE.md/AGENTS.md) use
    the onboarding names. Only before the seed commit (the re-render lands in
    it) or when the profile is missing (fresh clone); otherwise just advise,
    because a re-render would dirty committed framework files."""
    from . import restore
    prof = state.read_operator_profile(root)
    ident = brain.get("identity") or {}
    differs = (prof.get("operator_name"), prof.get("assistant_name")) != \
        (ident.get("operator_name"), ident.get("assistant_name"))
    if not differs:
        return
    if seed or not prof:
        try:
            print("identity: %s" % restore.run(root)["result"])
        except (state.BrainError, OSError, subprocess.SubprocessError) as exc:
            state.log_error(root, "identity sync failed: %s" % exc, "apply")
        return
    print("identity: operator/profile.json names differ from brain.json; run "
          "`python3 scripts/brain/onboard.py restore` and commit the re-rendered files")


def run_learn(root: Path) -> None:
    """ws-learn's indexer + warn-only git hooks, only if that tool is present."""
    tool = root / "scripts" / "brain" / "tessbrain.py"
    if not tool.exists() or os.environ.get("TESS_BRAIN_NO_LEARN"):
        return
    for args in (["index", "--quiet"], ["githooks", "install"]):
        try:
            done = subprocess.run([sys.executable, str(tool)] + args, cwd=str(root),
                                  capture_output=True, text=True, timeout=120)
            if done.returncode != 0:
                state.log_error(root, "tessbrain.py %s exited %d" % (" ".join(args), done.returncode),
                                (done.stderr or "").strip()[-300:])
        except (OSError, subprocess.TimeoutExpired) as exc:
            state.log_error(root, "tessbrain.py %s failed: %s" % (" ".join(args), exc))


# ------------------------------------------------------------------ run -----

def run(root: Path, dry: bool = False, final_status: str = "complete") -> Dict[str, Any]:
    st = state.status_of(root)
    if st["status"] == "source-repo":
        raise state.BrainError("this is the Tess OS source repo: apply refuses. Install an instance "
                               "with `npm create tess@latest <folder>` or run convert-clone.", 3)
    brain = state.load_brain(root)
    done_before = brain is not None and brain["onboarding"].get("status") in ("complete", "skipped")
    if brain is None or not (done_before or answers.all_answered(brain)):
        raise state.BrainError("onboarding is not complete (%s/7): answer the remaining steps first"
                               % st.get("step"), 3)
    finalize_brain(brain)
    ctx = build_ctx(brain)
    plan = scaffold.Plan(root, dry)
    gi_changed = gitignore.ensure_block(root, dry)
    scaffold.core_seeds(plan, ctx)
    scaffold_modes(plan, brain, ctx, brain["modes"])
    chart.write(plan)
    rid = records.mode_decision(plan, brain, ctx)
    records.probe_seed(plan, brain, rid)
    onb = brain["onboarding"]
    if not done_before:
        onb.update({"status": final_status, "step": state.TOTAL_STEPS,
                    "completed_at": state.now_iso(brain.get("timezone"))})
    result = {"status": onb["status"], "dry_run": dry, "decision": rid, "commit": None,
              "created": plan.created(),
              "skipped": sum(1 for a, _ in plan.actions if a == "skipped (exists)")}
    if dry:
        return result
    state.save_brain(root, brain)
    run_learn(root)
    sync_identity(root, brain, seed=git(root, "rev-parse", "--verify", "-q", "HEAD").returncode != 0)
    msg = "brain: onboarding apply (%s)" % ", ".join(brain["modes"] + brain["presets"])
    result["commit"] = commit_brain(root, msg, [".gitignore"] if gi_changed else [])
    return result


def print_summary(result: Dict[str, Any], brain: Optional[Dict[str, Any]]) -> None:
    verb = "would create" if result["dry_run"] else "created"
    print("apply: %s %d file(s), %d already present." % (verb, len(result["created"]), result["skipped"]))
    tops = sorted({"/".join(p.split("/")[:3]) + "/" for p in result["created"] if p.count("/") >= 3})
    for top in tops:
        print("  %s" % top)
    if result.get("decision"):
        print("decision: brain/decisions/%s.md (pending-verification)" % result["decision"])
    if result.get("commit"):
        print("committed: %s" % result["commit"])
    if not result["dry_run"] and brain:
        first = _first_entity(brain)
        print("Try: \"Tell me about %s\" | \"What did we decide about the brain mode?\" | "
              "\"From now on, ...\"" % first)
        print(SEED_PUSH)


def _first_entity(brain: Dict[str, Any]) -> str:
    for field in ("clients", "units", "projects", "areas"):
        names = value(brain, field) or []
        if names:
            return names[0]
    return brain.get("modes", ["personal"])[0]
