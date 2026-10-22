"""The conversation note's summary block and its privacy rules (used by journal.py).

A committed note must not carry private content. When any tool call in the
session named a private path (`.private/`, the private overlay `clients/`,
the root `kb/`) the replies are withheld, and those paths are never listed as
files touched. Paths are judged relative to the instance root, so an instance
that itself lives under a folder called `clients/` is not affected.
"""
from __future__ import annotations

import os
from typing import Dict, List

from . import cues, privacy
from .config import Config
from .parsers import Session, is_private_path
from .textutil import clip

WITHHELD = ("[reply withheld: this session read a private path or searched broadly; "
            "see the local transcript]")


def _local(cfg: Config, sess: Session, text: str) -> str:
    """`text` with the instance root and the session cwd made relative, so only paths inside
    the instance (or outside it altogether) are judged by is_private_path."""
    for base in {str(cfg.root), os.path.realpath(str(cfg.root)), sess.cwd or ""}:
        if base and base != "/":
            text = text.replace(base.rstrip("/") + "/", " ")
    return text


def private_read(cfg: Config, sess: Session) -> bool:
    """True when any tool call in the session named a private path (.private/, clients/, kb/), or when the
    parser could not keep every place a tool input named one (then the replies are withheld to be safe)."""
    if getattr(sess, "inspection_incomplete", False):
        return True
    if any(is_private_path(_local(cfg, sess, t)) for t in getattr(sess, "tool_inputs", [])):
        return True
    # v1.0.0 item d (Cyra M-3): a cd into the instance, a glob, a recursive search, a variable-expanded
    # path, or a Grep/Glob over the root or a private dir can read private content without naming it.
    return privacy.broad_access(str(cfg.root), sess.cwd or "", getattr(sess, "broad_shell", False),
                                getattr(sess, "cd_targets", []), getattr(sess, "search_paths", []))


def private_file(cfg: Config, sess: Session, path: str) -> bool:
    return is_private_path(_local(cfg, sess, " " + path))


def summary(part: List, with_text: bool, files: List[str], withheld: bool) -> List[str]:
    """Deterministic summary of one part: span, counts, opening line, key facts flagged. No LLM."""
    msgs = [e for e in part if e.kind == "msg"]
    ops = [e for e in msgs if e.principal]
    reps = [e for e in part if e.kind == "reply"]
    kinds: Dict[str, int] = {}
    for e in ops:
        for hit in cues.scan_text(e.text):
            kinds[hit.kind] = kinds.get(hit.kind, 0) + 1
    span = "%s-%s" % (part[0].hhmm, part[-1].hhmm) if part else "-"
    out = ["- Span %s: %d operator message(s), %d other, %d repl%s%s." % (
        span, len(ops), len(msgs) - len(ops), len(reps), "y" if len(reps) == 1 else "ies",
        " (withheld: private paths read)" if withheld else "")]
    if with_text and ops:
        out.append('- Opened with (%s): "%s"' % (ops[0].label, clip(" ".join(ops[0].text.split()), 160)))
    facts = ", ".join("%d %s" % (n, k) for k, n in sorted(kinds.items()))
    out.append("- Key facts flagged: %s%s." % (facts or "none", " (see Heuristic flags; records link back here)"
                                                if facts else ""))
    out.append("- Files touched: %d." % len(files))
    return out
