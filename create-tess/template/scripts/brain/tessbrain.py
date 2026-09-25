#!/usr/bin/env python3
"""tessbrain.py: the Tess OS learning loop (stdlib only, Python 3.9+).

Every conversation noted; smarter after every exchange; never a record
without the principal's own verbatim words. See docs/brain/LEARNING.md.

  sync        journal new transcript records, cue pass, verify, promote, index
  journal note  note a conversation by hand (runtimes without capture hooks)
  decide      record a principal's decision (verbatim quote, V1-V9)
  remember    record a preference, correction, fact or open loop
  inbox       add | list | verify candidates (the brain-distill skill uses add)
  promote     promote a reviewed inbox candidate with the operator's approval
  confirm | reject | retract   change a record, backed by the principal's words
  review      numbered list of what awaits the operator
  index       regenerate indexes and START HERE blocks (exit 3 over a cap)
  lint        record integrity, reachability, people deny-list, budgets
  status      saved? (committed + pushed + reachable), learned, review, errors
  save        path-scoped commit of brain/ (+ push when safe); hooks always run
  recall      grep-grade search of brain/ with path:line results
  hook        session-start | prompt | stop handlers for Claude Code and Codex
  githooks    install the warn-only git hooks
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brainlib import commands as C  # noqa: E402
from brainlib import hooks as H  # noqa: E402
from brainlib.config import Config, default_root, log_error  # noqa: E402


def _quote_args(p, statement=True):
    p.add_argument("--quote", required=True, help="the principal's exact words (verbatim)")
    if statement:
        p.add_argument("--statement", default="", help="the record's statement (defaults to the quote)")
    p.add_argument("--source-ref", default="", help="brain/journal/...md#L<n> (found automatically if omitted)")
    p.add_argument("--speaker", default="", help="principal slug (checked against the source line)")
    p.add_argument("--supersedes", default="")
    p.add_argument("--entity", default="", help="entity id, e.g. clients/acme")
    p.add_argument("--dry-run", action="store_true")


def _record_parsers(sub):
    d = sub.add_parser("decide", help="record a principal's decision")
    _quote_args(d)
    d.add_argument("--register", default="", help="e.g. brain/clients/acme/decisions (default brain/decisions)")
    d.add_argument("--title", default="")
    d.add_argument("--tier", choices=["routine", "material"], default="routine")
    d.add_argument("--kind", dest="decision_kind", default="decision",
                   choices=["decision", "requirement", "constraint", "question"])
    d.add_argument("--approves-quote", default="", help="the assistant proposal being approved (verbatim)")
    d.add_argument("--also-quoted", action="append", default=[])
    d.add_argument("--no-sync", action="store_true")
    d.set_defaults(fn=C.cmd_decide)
    r = sub.add_parser("remember", help="record a preference, correction, fact or open loop")
    r.add_argument("--kind", required=True, choices=["preference", "correction", "fact", "open_loop"])
    _quote_args(r)
    for opt in ("--due", "--owner", "--verify-via"):
        r.add_argument(opt, default="")
    r.add_argument("--no-sync", action="store_true")
    r.set_defaults(fn=C.cmd_remember)
    for action in ("confirm", "reject", "retract"):
        s = sub.add_parser(action, help="%s a record (or reject a candidate) with the principal's words" % action)
        s.add_argument("id")
        s.add_argument("--quote", required=True)
        s.set_defaults(fn=C.cmd_status_change, action=action)
    pr = sub.add_parser("promote", help="promote a reviewed inbox candidate (operator approval quote)")
    pr.add_argument("id")
    pr.add_argument("--quote", required=True)
    pr.set_defaults(fn=C.cmd_promote)


def _inbox_parsers(sub):
    ib = sub.add_parser("inbox", help="candidates").add_subparsers(dest="inbox_cmd", required=True)
    add = ib.add_parser("add", help="propose a typed candidate (verified before anything is written)")
    add.add_argument("--kind", required=True, choices=["decision", "preference", "correction", "fact", "open_loop",
                                                        "skill"])
    _quote_args(add)
    add.add_argument("--title", default="")
    add.add_argument("--tier", choices=["routine", "material"], default="routine")
    add.add_argument("--register", default="")
    add.add_argument("--detected-by", default="distill", choices=["cue", "distill", "decide", "onboarding", "operator"])
    for opt in ("--due", "--owner", "--verify-via", "--approves-quote"):
        add.add_argument(opt, default="")
    add.set_defaults(fn=C.cmd_inbox_add)
    ib.add_parser("list").set_defaults(fn=C.cmd_inbox_list)
    ib.add_parser("verify", help="dry-run the verifier over the inbox").set_defaults(fn=C.cmd_inbox_verify)


def _sync_parser(sub):
    s = sub.add_parser("sync", help="journal + cue pass + verify + promote + index")
    s.add_argument("--runtime", choices=["all", "claude", "codex", "gemini"], default="all")
    s.add_argument("--claude-dir", default=None, help="directory of Claude transcripts (default: this project's)")
    s.add_argument("--codex-home", default=None, help="CODEX_HOME to sweep (default $CODEX_HOME or ~/.codex)")
    s.add_argument("--gemini-home", default=None, help="HOME whose .gemini/ to sweep (default $GEMINI_CLI_HOME or ~)")
    s.add_argument("--also-cwd", action="append", default=[], help="extra Codex session cwd to accept (moved repo)")
    s.add_argument("--transcript", default=None, help="journal just this transcript file")
    s.add_argument("--days", type=int, default=None, help="only transcripts touched in the last N days")
    s.add_argument("--no-wait", action="store_true", help="skip if another sync holds the lock")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(fn=C.cmd_sync)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tessbrain.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="instance root (default: the repo holding this script)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)
    _sync_parser(sub)
    j = sub.add_parser("journal", help="journal tools").add_subparsers(dest="journal_cmd", required=True)
    n = j.add_parser("note", help="note a conversation turn by hand (runtimes without capture hooks)")
    n.add_argument("--text", required=True)
    n.add_argument("--speaker", default="", help="principal slug or alias (default: this machine's user)")
    n.set_defaults(fn=C.cmd_journal_note)
    _record_parsers(sub)
    _inbox_parsers(sub)
    sub.add_parser("review", help="what awaits the operator").set_defaults(fn=C.cmd_review)
    i = sub.add_parser("index", help="regenerate generated files and marker blocks")
    i.add_argument("--quiet", action="store_true")
    i.set_defaults(fn=C.cmd_index)
    li = sub.add_parser("lint", help="integrity checks (exit 1 on error)")
    li.add_argument("--staged", action="store_true")
    li.add_argument("--warn-only", action="store_true")
    li.set_defaults(fn=C.cmd_lint)
    sub.add_parser("status", help="saved? learned? review? errors?").set_defaults(fn=C.cmd_status)
    sv = sub.add_parser("save", help="path-scoped commit of brain/ (+ push when safe)")
    sv.add_argument("-m", "--message", default="brain: save")
    sv.add_argument("--dry-run", action="store_true")
    sv.set_defaults(fn=C.cmd_save)
    rc = sub.add_parser("recall", help="search brain/ (path:line results)")
    rc.add_argument("query")
    rc.add_argument("--entity", default=None)
    rc.add_argument("--type", default=None)
    rc.add_argument("--limit", type=int, default=20)
    rc.add_argument("--private", action="store_true")
    rc.set_defaults(fn=C.cmd_recall)
    h = sub.add_parser("hook", help="runtime hook handler (always exits 0)")
    h.add_argument("event", choices=["session-start", "prompt", "stop"])
    h.add_argument("--runtime", choices=["claude", "codex"], default="claude")
    g = sub.add_parser("githooks", help="git hooks").add_subparsers(dest="githooks_cmd", required=True)
    g.add_parser("install", help="warn-only pre-commit lint + post-merge index").set_defaults(fn=C.cmd_githooks)
    sub.add_parser("distilled", help="mark the turns distilled so far").set_defaults(fn=C.cmd_distilled)
    return ap


def _print(payload, as_json: bool) -> None:
    if payload is None:
        return
    if as_json or not isinstance(payload, str):
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    else:
        print(payload)


def _globals(argv):
    """--json and --root are accepted anywhere on the command line."""
    rest, as_json, root, i = [], False, None, 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--root" and i + 1 < len(argv):
            root, i = argv[i + 1], i + 1
        elif a.startswith("--root="):
            root = a.split("=", 1)[1]
        else:
            rest.append(a)
        i += 1
    return rest, as_json, root


def main(argv=None) -> int:
    rest, as_json, root_arg = _globals(list(sys.argv[1:] if argv is None else argv))
    args = build_parser().parse_args(rest)
    args.json = as_json
    root = Path(root_arg).resolve() if root_arg else default_root()
    if args.cmd == "hook":
        return H.dispatch(root, args.event, args.runtime)
    cfg = Config(root)
    try:
        code, payload = args.fn(cfg, args)
    except Exception as exc:  # noqa: BLE001 - logged with context, then non-zero
        log_error(cfg, "%s failed" % args.cmd, exc)
        return 1
    if not getattr(args, "quiet", False) or code != 0:
        _print(payload, args.json)
    return code


if __name__ == "__main__":
    sys.exit(main())
