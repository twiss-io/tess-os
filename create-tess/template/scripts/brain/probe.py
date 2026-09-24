#!/usr/bin/env python3
"""Static fresh-clone probe: can a zero-context agent answer from files alone?

  python3 scripts/brain/probe.py --static [--json] [--root DIR]

Answers the questions in brain/probe.json by ROUTING through the files the
way a new agent would (brain/START-HERE.md -> each entity's AGENTS.md ->
brain/decisions/), never by reading the expected answers back. Each answer
is then compared with the expectation onboarding seeded in probe.json.

Pass (exit 0): at least 4 of the 5 questions answered correctly AND the
negative-control question answered "unknown" (the brain must not contain
what it should never hold). Exit 1: fewer correct answers, a failed negative
control, or no onboarded brain at all (no brain/brain.json, no probe.json,
no START-HERE.md). Exit 2: usage. Stdlib only, python3 >= 3.9, no network.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True
PASS_AT = 4
START_HERE = "brain/START-HERE.md"
_LINK = re.compile(r"\]\(([^)]+)\)")
_BANK = re.compile(r"(?i)\b(bank|iban|account)\b[^\n]{0,40}?\d[\d -]{5,}\d")


def read(root: Path, rel: str) -> Optional[str]:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def front_matter(text: str) -> Dict[str, Any]:
    """Flat `key: value` front matter; JSON-quoted values are decoded."""
    if not text.startswith("---\n"):
        return {}
    out: Dict[str, Any] = {}
    for line in text[4:].split("\n---", 1)[0].splitlines():
        key, sep, raw = line.partition(":")
        if not sep or line.startswith(" "):
            continue
        raw = raw.strip()
        try:
            out[key.strip()] = json.loads(raw)
        except ValueError:
            out[key.strip()] = raw
    return out


def section(text: str, heading: str) -> List[str]:
    lines = text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == heading)
    except StopIteration:
        return []
    out = []
    for ln in lines[start + 1:]:
        if ln.startswith("## "):
            break
        out.append(ln)
    return out


def ask_mode(root: Path, start: str) -> Tuple[Any, str]:
    m = re.search(r"(?m)^- Mode: (.+?) \(primary: ", start)
    modes = [x.strip() for x in m.group(1).split(",")] if m else None
    return modes, "%s `- Mode:` line" % START_HERE


def ask_operator(root: Path, start: str) -> Tuple[Any, str]:
    m = re.search(r"(?m)^- Operator: (.+?) \(address as ", start)
    return (m.group(1).strip() if m else None), "%s `- Operator:` line" % START_HERE


def ask_entities(root: Path, start: str) -> Tuple[Any, str]:
    """Every row in `## Entities` whose link resolves to an AGENTS.md with START HERE."""
    found = []
    for line in section(start, "## Entities"):
        m = _LINK.search(line) if line.startswith("|") else None
        if not m:
            continue
        target = os.path.normpath(os.path.join("brain", m.group(1))).replace(os.sep, "/")
        head = "\n".join((read(root, target) or "").splitlines()[:80])
        if target.endswith("/AGENTS.md") and re.search(r"(?m)^# START HERE", head):
            found.append(target[len("brain/"):-len("/AGENTS.md")])
    return sorted(found), "%s `## Entities` rows -> each AGENTS.md (START HERE)" % START_HERE


def ask_first_decision(root: Path, start: str) -> Tuple[Any, str]:
    ddir = root / "brain" / "decisions"
    files = sorted(ddir.glob("D-*.md")) if ddir.is_dir() else []
    if not files or "brain/decisions/" not in start:
        return None, "brain/decisions/ (not reachable from START-HERE)"
    fm = front_matter(files[0].read_text(encoding="utf-8"))
    return {"id": fm.get("id"), "quote": fm.get("source_quote")}, "brain/decisions/%s" % files[0].name


def ask_research(root: Path, start: str) -> Tuple[Any, str]:
    for line in section(start, "## Where things go"):
        if line.startswith("| Research"):
            m = re.search(r"`(brain/[^`]*?/)[^`/]*`", line)
            if m and (root / m.group(1)).is_dir():
                return m.group(1), "%s `Where things go` Research row" % START_HERE
    return None, "%s `Where things go` (no Research row)" % START_HERE


ASK = {"mode": ask_mode, "operator": ask_operator, "entities": ask_entities,
       "first-decision": ask_first_decision, "research": ask_research}


def negative_control(root: Path) -> Tuple[str, str]:
    """'unknown' unless a committed brain file holds something bank-account-shaped."""
    for path in sorted((root / "brain").rglob("*")):
        rel = path.relative_to(root).as_posix()
        if not path.is_file() or "/.private/" in rel or path.suffix not in (".md", ".json", ".txt"):
            continue
        hit = _BANK.search(path.read_text(encoding="utf-8", errors="ignore"))
        if hit:
            return "found", rel
    return "unknown", "no brain file holds it"


def run(root: Path) -> Dict[str, Any]:
    missing = [p for p in ("brain/brain.json", "brain/probe.json", START_HERE) if not (root / p).is_file()]
    if missing:
        return {"result": "fail", "reason": "not an onboarded brain: missing %s" % ", ".join(missing),
                "score": 0, "total": 0, "answers": []}
    probe = json.loads(read(root, "brain/probe.json") or "{}")
    start = read(root, START_HERE) or ""
    answers = []
    for q in probe.get("questions", []):
        fn = ASK.get(q.get("id"))
        got, source = fn(root, start) if fn else (None, "no routine for this question")
        answers.append({"id": q.get("id"), "ask": q.get("ask"), "answer": got, "expect": q.get("expect"),
                        "ok": got is not None and got == q.get("expect"), "source": source})
    neg = probe.get("negative_control") or {}
    got, source = negative_control(root)
    neg_out = {"id": neg.get("id"), "ask": neg.get("ask"), "answer": got, "source": source,
               "ok": got == neg.get("expect", "unknown")}
    score = sum(1 for a in answers if a["ok"])
    passed = score >= min(PASS_AT, len(answers)) and len(answers) > 0 and neg_out["ok"]
    return {"result": "pass" if passed else "fail", "score": score, "total": len(answers),
            "answers": answers, "negative_control": neg_out}


def print_text(out: Dict[str, Any]) -> None:
    if out.get("reason"):
        print("probe: FAIL (%s)" % out["reason"])
        return
    for a in out["answers"] + [out["negative_control"]]:
        print("[%s] %s -> %s  (%s)" % ("ok" if a["ok"] else "XX", a["ask"],
                                       json.dumps(a["answer"], ensure_ascii=False), a["source"]))
    print("probe: %s (%d/%d, negative control %s)" % (out["result"].upper(), out["score"], out["total"],
                                                       "ok" if out["negative_control"]["ok"] else "FAILED"))


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="probe.py", description=__doc__.split("\n")[0])
    p.add_argument("--static", action="store_true", help="answer from files alone (required)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--root", default=os.environ.get("TESS_BRAIN_ROOT") or ".")
    args = p.parse_args(argv)
    if not args.static:
        p.error("only --static is implemented; the live-model probe is tests/smoke/brain_oobe_live.sh")
    out = run(Path(args.root).resolve())
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print_text(out)
    return 0 if out["result"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
