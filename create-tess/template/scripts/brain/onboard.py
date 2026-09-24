#!/usr/bin/env python3
"""Tess OS second-brain onboarding CLI (stdlib only, python3 >= 3.9).

  status [--json]                      pending | in_progress(step) | complete | deferred | skipped | source-repo
  answer [FIELD] --step N --field K --value V --quote "<operator's exact words>"
  init [--mode M] [--preset P] [--operator NAME] [--non-interactive] [--answers F] [--until-step N]
  apply [--dry-run] [--json]           scaffold + first decision + path-scoped commit (exit 3 if not ready)
  add client|person|project|area|unit|seat "<name>" [--in PARENT]
  add-mode personal|agency|organisation --quote "..."
  defer [--days 7]  |  skip --quote "..."  |  restore  |  convert-clone [--yes]
  hook session-start --runtime claude|codex

Exit codes: 0 ok, 2 usage/validation, 3 refused (not ready / source repo), 4 git or tessctl failure.
Docs: docs/brain/ONBOARDING.md.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # never leave __pycache__/ in a brain repo's working tree
sys.path.insert(0, str(Path(__file__).resolve().parent))

from oobe import answers, apply, chart, convert, entities, hook, records, restore, scaffold, state  # noqa: E402

TOTAL = state.TOTAL_STEPS


def _emit(obj, as_json: bool, text: str) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False) if as_json else text)


def _brain_or_new(root: Path) -> dict:
    if state.is_source_repo(root):
        raise state.BrainError("this is the Tess OS source repo: onboarding is off here. "
                               "Run `npm create tess@latest <folder>`, or convert-clone.", 3)
    return state.load_brain(root) or state.default_brain(root)


def cmd_status(root: Path, a) -> int:
    st = state.status_of(root)
    if st["status"] in ("pending", "in_progress"):
        brain = state.load_brain(root) or {}
        st["next_question"] = answers.question_for(st["step"] or 1, brain)
        st["detected_timezone"] = state.detect_timezone()
        st["missing"] = [f for f in answers.required_fields(st["step"] or 1, brain)
                         if f not in answers.answered(brain)]
    _emit(st, a.json, "onboarding: %s" % state.status_line(st))
    return 0


def cmd_answer(root: Path, a) -> int:
    field = a.field or a.key
    if not field:
        raise state.BrainError("answer needs a field (positional or --field)")
    brain = _brain_or_new(root)
    if brain["onboarding"].get("status") in ("complete", "skipped"):
        raise state.BrainError("onboarding is already %s; use add / add-mode" % brain["onboarding"]["status"], 3)
    if a.step and answers.FIELD_STEP.get(field) != a.step:
        raise state.BrainError("field %s belongs to step %s, not %s" % (field, answers.FIELD_STEP.get(field), a.step))
    entry = answers.record(brain, field, a.value, a.quote, a.runtime, a.session, a.at)
    state.save_brain(root, brain)
    st = state.status_of(root)
    _emit({"recorded": field, "value": entry["value"], "status": st}, a.json,
          "recorded %s = %s; onboarding: %s" % (field, json.dumps(entry["value"]), state.status_line(st)))
    return 0


def _load_answers_file(path: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise state.BrainError("cannot read answers file %s: %s" % (path, exc))
    if not isinstance(data, dict) or not isinstance(data.get("answers"), list):
        raise state.BrainError("answers file needs {\"answers\": [{step, field, value, quote}, ...]}")
    return data


def cmd_init(root: Path, a) -> int:
    brain = _brain_or_new(root)
    if brain["onboarding"].get("status") in ("complete", "skipped"):
        raise state.BrainError("onboarding is already complete", 3)
    until = a.until_step or TOTAL
    if a.answers:
        data = _load_answers_file(a.answers)
        for item in sorted(data["answers"], key=lambda i: int(i.get("step", 0))):
            if int(item.get("step", 0)) <= until:
                answers.record(brain, item["field"], item["value"], item.get("quote", ""),
                               item.get("runtime") or data.get("runtime", "answers-file"),
                               item.get("session") or data.get("session", ""), item.get("at", ""))
    flags = [("mode", a.mode, "--mode"), ("preset", a.preset, "--preset"),
             ("operator_name", a.operator, "--operator"), ("assistant_name", a.assistant, "--assistant")]
    for field, val, flag in flags:
        if val is not None and answers.FIELD_STEP[field] <= until:
            answers.record(brain, field, val, "%s %s" % (flag, val), "cli", "", "")
    if a.non_interactive:
        answers.fill_defaults(brain, until)
    state.save_brain(root, brain)
    st = state.status_of(root)
    _emit(st, a.json, "onboarding: %s%s" % (state.status_line(st), " (ready: run apply)" if st["ready_to_apply"] else ""))
    return 0


def cmd_apply(root: Path, a) -> int:
    result = apply.run(root, dry=a.dry_run)
    if a.json:
        _emit(result, True, "")
    else:
        apply.print_summary(result, state.load_brain(root))
    return 0


def _require_complete(root: Path) -> dict:
    brain = state.load_brain(root)
    if brain is None or brain["onboarding"].get("status") not in ("complete", "skipped"):
        raise state.BrainError("finish onboarding first (status, then apply)", 3)
    return brain


def cmd_add(root: Path, a) -> int:
    brain = _require_complete(root)
    plan = scaffold.Plan(root, a.dry_run)
    ctx = apply.build_ctx(brain)
    extra = {"holder": "unfilled"} if a.kind == "seat" else {}
    dest = entities.add(plan, brain, ctx, a.kind, a.name, parent=a.parent, mode=a.mode, extra=extra)
    if a.kind == "seat":
        chart.write(plan)
    for action, path in plan.actions:
        print("%s: %s" % (action, path))
    print("%s %s -> %s (not committed yet: save with the brain-save skill or git)" % (a.kind, a.name, dest))
    return 0


def cmd_add_mode(root: Path, a) -> int:
    brain = _require_complete(root)
    mode = answers.parse_modes(a.mode)[0]
    if mode in brain.get("modes", []):
        print("skipped (exists): mode %s is already active" % mode)
        return 0
    brain["modes"] = list(brain.get("modes", [])) + [mode]
    brain["entity_roots"] = scaffold.entity_roots(brain["modes"])
    plan = scaffold.Plan(root, a.dry_run)
    ctx = apply.build_ctx(brain)
    entities.add_base(plan, scaffold.load_manifest("modes", mode), ctx)
    chart.write(plan)
    entry = {"quote": a.quote, "at": state.now_iso(brain.get("timezone")), "runtime": a.runtime or "cli",
             "session": ""}
    rid = records.mode_decision(plan, brain, ctx, slug="add-mode-%s" % mode,
                                title="Add brain mode: %s" % mode, entry=entry)
    entities.update_mode_line(plan, apply.modes_line(brain["modes"]))
    if not a.dry_run:
        state.save_brain(root, brain)
    for action, path in plan.actions:
        print("%s: %s" % (action, path))
    print("mode %s added (decision %s); nothing was moved or renamed" % (mode, rid))
    return 0


def cmd_defer(root: Path, a) -> int:
    brain = _brain_or_new(root)
    if brain["onboarding"].get("status") in ("complete", "skipped"):
        raise state.BrainError("onboarding is already complete", 3)
    when = _dt.datetime.now().astimezone() + _dt.timedelta(days=a.days)
    brain["onboarding"].update({"status": "deferred", "remind_after": when.replace(microsecond=0).isoformat()})
    state.save_brain(root, brain)
    print("onboarding deferred until %s" % brain["onboarding"]["remind_after"])
    return 0


def cmd_skip(root: Path, a) -> int:
    brain = _brain_or_new(root)
    if "mode" not in answers.answered(brain):
        answers.record(brain, "mode", "personal", a.quote, a.runtime or "cli", "", "")
    answers.fill_defaults(brain, TOTAL)
    state.save_brain(root, brain)
    result = apply.run(root, final_status="skipped")
    apply.print_summary(result, state.load_brain(root))
    return 0


def cmd_restore(root: Path, a) -> int:
    out = restore.run(root, a.dry_run)
    _emit(out, a.json, "restore: %s (%s / %s)" % (out["result"], out["operator_name"], out["assistant_name"]))
    return 0


def cmd_convert(root: Path, a) -> int:
    steps = convert.run(root, a.yes)
    for step in steps:
        print("%s %s" % ("done:" if a.yes else "plan:", step))
    if not a.yes:
        print("re-run with --yes to convert this clone")
    return 0


def cmd_hook(root: Path, a) -> int:
    return hook.session_start(root, a.runtime)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="onboard.py", description=__doc__.split("\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("status"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("answer")
    s.add_argument("key", nargs="?"); s.add_argument("--step", type=int); s.add_argument("--field")
    s.add_argument("--value", required=True); s.add_argument("--quote", default="")
    s.add_argument("--runtime", default=""); s.add_argument("--session", default="")
    s.add_argument("--at", default=""); s.add_argument("--json", action="store_true")
    s = sub.add_parser("init")
    for flag in ("--mode", "--preset", "--operator", "--assistant", "--answers"):
        s.add_argument(flag)
    s.add_argument("--non-interactive", action="store_true"); s.add_argument("--until-step", type=int)
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("apply"); s.add_argument("--dry-run", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("add")
    s.add_argument("kind"); s.add_argument("name"); s.add_argument("--in", dest="parent")
    s.add_argument("--mode"); s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("add-mode")
    s.add_argument("mode"); s.add_argument("--quote", required=True); s.add_argument("--runtime", default="")
    s.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("defer"); s.add_argument("--days", type=int, default=7)
    s = sub.add_parser("skip"); s.add_argument("--quote", required=True); s.add_argument("--runtime", default="")
    s = sub.add_parser("restore"); s.add_argument("--dry-run", action="store_true"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("convert-clone"); s.add_argument("--yes", action="store_true")
    s = sub.add_parser("hook"); s.add_argument("event", choices=["session-start"])
    s.add_argument("--runtime", default="claude", choices=["claude", "codex"])
    return p


COMMANDS = {"status": cmd_status, "answer": cmd_answer, "init": cmd_init, "apply": cmd_apply,
            "add": cmd_add, "add-mode": cmd_add_mode, "defer": cmd_defer, "skip": cmd_skip,
            "restore": cmd_restore, "convert-clone": cmd_convert, "hook": cmd_hook}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not args.cmd:
        build_parser().print_help()
        return 2
    root = state.find_root()
    try:
        return COMMANDS[args.cmd](root, args)
    except state.BrainError as exc:
        if args.cmd == "hook":
            state.log_error(root, str(exc), "hook")
            return 0
        state.log_error(root, str(exc), args.cmd)
        return exc.code
    except Exception as exc:  # never a bare traceback from a hook
        state.log_error(root, "unexpected %s: %s" % (type(exc).__name__, exc), args.cmd)
        if args.cmd == "hook":
            return 0
        raise


if __name__ == "__main__":
    sys.exit(main())
