"""Deterministic, redacted journal: one file per session (spec section 9.4).

The note is a summary plus the evidence, not a transcript dump: a `## Summary`
block (span, counts, what the session opened with, key facts flagged), the
operator's own lines (the evidence every record's quote is checked against),
short reply excerpts, and the flags. Tool input and output, system text and
injected instructions are never kept. When any tool call in the session named
a private path (`.private/`, the private overlay `clients/`, the root `kb/`),
the replies are withheld and those paths are left out of "Files touched".

The session file is a pure function of the transcript prefix up to the
cursor, so a re-run with no new records writes nothing and a re-run after
new records adds lines and refreshes only the Summary block (labels L<n>/R<n>
never move). No LLM involved.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import cues, frontmatter, gitutil, lookup, redact
from .notes import WITHHELD, private_read, private_file, summary
from .config import Config, iso, read_json, write_json, write_text_if_changed
from .parsers import AUTOMATION, Session, count_lines, to_automation
from .textutil import clip

SPLIT_BYTES = 256 * 1024
REPLY_CHARS = 600
ORDER = ["schema", "type", "runtime", "runtime_version", "session_id", "part", "source_path",
         "source_sha256", "started_at", "updated_at", "cwd", "git_branch", "git_head", "entities",
         "external_context", "redactions", "speakers", "turns", "stub"]


class Entry:
    __slots__ = ("label", "hhmm", "speaker", "channel", "text", "principal", "at", "ordinal", "kind", "ref")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def _rel_file(cfg: Config, path: str) -> str:
    """A touched file relative to the instance root; outside it, only the file name."""
    real = os.path.realpath(os.path.join(sess_root(cfg), path)) if path else ""
    root = os.path.realpath(str(cfg.root))
    if real.startswith(root + os.sep):
        return Path(os.path.relpath(real, root)).as_posix()
    return "(outside the instance) %s" % os.path.basename(path or "")


def sess_root(cfg: Config) -> str:
    return str(cfg.root)


def _hhmm(cfg: Config, at: str) -> str:
    try:
        return cfg.local(at).strftime("%H:%M")
    except (ValueError, TypeError):
        return "--:--"


def base_relpath(cfg: Config, sess: Session) -> str:
    """brain-relative path: journal/YYYY/MM/DD/HHMM-<runtime>-<sid8>.md."""
    start = sess.started_at or (sess.msgs[0].at if sess.msgs else "")
    try:
        t = cfg.local(start)
    except (ValueError, TypeError):
        t = cfg.now()
    alnum = "".join(c for c in sess.session_id if c.isalnum())
    rel = "journal/%s/%s-%s-%s.md" % (t.strftime("%Y/%m/%d"), t.strftime("%H%M"), sess.runtime, alnum[:8] or "session")
    owner = _owner(cfg, rel)
    if owner and owner != sess.session_id:
        # Two sessions in one minute whose ids share 8 leading characters: codex-cli ids are UUIDv7, so
        # their first 8 hex digits are a timestamp. Found live 2026-09-29: the second session overwrote the
        # first's note and its decision's source_ref pointed at the wrong words. The later one gets the id tail.
        rel = rel[:-3] + "-" + (alnum[-8:] or "2") + ".md"
    return rel


def _owner(cfg: Config, rel: str) -> str:
    """session_id recorded in the front matter of an existing journal file (committed or local body)."""
    for base in (cfg.brain, cfg.state):
        path = base / rel
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", errors="replace") as fh:
            for _, line in zip(range(40), fh):
                if line.startswith("session_id:"):
                    return line.split(":", 1)[1].strip().strip('"')
    return ""


def build_entries(cfg: Config, sess: Session, sticky: bool = False) -> Tuple[List[Entry], Dict[str, int]]:
    """`sticky`: an earlier sync of this transcript already saw a private read, so replies stay withheld."""
    counts: Dict[str, int] = {}
    withhold = sticky or private_read(cfg, sess)
    entries: List[Entry] = []
    nl = 0
    for m in sess.msgs:
        text, c = redact.redact(m.text)
        for k, v in c.items():
            counts[k] = counts.get(k, 0) + v
        if m.role == "assistant":  # R<k> is the final reply after message L<k> (R0: before any message)
            if withhold:
                text = WITHHELD
            elif len(text) > REPLY_CHARS:
                text = text[:REPLY_CHARS].rstrip() + " [... see transcript]"
            entries.append(Entry(label="R%d" % nl, hhmm=_hhmm(cfg, m.at), speaker="assistant", channel="reply",
                                 text=text, principal=False, at=m.at, ordinal=m.ordinal, kind="reply"))
            continue
        nl += 1
        slug = cfg.resolve_speaker(m.raw_speaker)
        ok = bool(slug) and cfg.consents(slug)
        shown = text if ok else ("[prompt omitted: sent by a headless or agent-started run, not typed by the "
                                 "operator]" if m.raw_speaker == AUTOMATION else
                                 "[non-principal %s omitted: no consent]" % m.raw_speaker)
        entries.append(Entry(label="L%d" % nl, hhmm=_hhmm(cfg, m.at), speaker=slug if ok else m.raw_speaker,
                             channel=m.channel, text=shown, principal=ok, at=m.at, ordinal=m.ordinal, kind="msg"))
    return entries, counts


def _line(e: Entry) -> str:
    lines = (e.text or "").splitlines() or [""]
    head = "[%s %s %s %s] %s" % (e.label, e.hhmm, e.speaker, e.channel, lines[0])
    return "\n".join([head] + ["  " + l for l in lines[1:]])


def _flags(entries: List[Entry], with_text: bool) -> List[str]:
    out = []
    for e in entries:
        if e.kind != "msg" or not e.principal:
            continue
        for hit in cues.scan_text(e.text):
            out.append("- %s %s: %s" % (e.label, hit.kind, '"%s"' % clip(hit.sentence, 160) if with_text else "(body local)"))
    return out


def _parts(entries: List[Entry]) -> List[List[Entry]]:
    parts: List[List[Entry]] = [[]]
    size = 0
    for e in entries:
        n = len(_line(e).encode("utf-8")) + 1
        if parts[-1] and size + n > SPLIT_BYTES:
            parts.append([])
            size = 0
        parts[-1].append(e)
        size += n
    return parts


def _body(sess: Session, part: List[Entry], through: int, title: str, with_text: bool, files: List[str]) -> str:
    msgs = [_line(e) for e in part if e.kind == "msg"]
    reps = [_line(e) for e in part if e.kind == "reply"]
    out = ["<!-- tess:session runtime=%s id=%s through=%d -->" % (sess.runtime, sess.session_id, through), "",
           "# %s" % title, ""]
    out += ["## Summary", ""] + summary(part, with_text, files, any(e.text == WITHHELD for e in part)) + [""]
    if with_text:
        out += ["## Messages", ""] + (msgs or ["(none)"]) + ["", "## Replies", ""] + (reps or ["(none)"]) + [""]
    out += ["## Heuristic flags", ""] + (_flags(part, with_text) or ["(none)"]) + [""]
    out += ["## Files touched", ""] + (["- %s" % f for f in files] or ["(none)"]) + [""]
    return "\n".join(out)


def render(cfg: Config, sess: Session, entity_ids: List[str], git_head: str,
           built: Optional[Tuple[List[Entry], Dict[str, int]]] = None) -> List[Tuple[str, str, Optional[str]]]:
    """-> [(brain-relative path, committed text, local-body text or None)]; sets Entry.ref."""
    entries, counts = built or build_entries(cfg, sess)
    policy = cfg.journal_policy
    base = base_relpath(cfg, sess)
    parts = _parts(entries)
    humans = [e for e in entries if e.kind == "msg"]
    last_at = entries[-1].at if entries else sess.started_at
    meta = {
        "schema": 1, "type": "journal-session", "runtime": sess.runtime, "runtime_version": sess.runtime_version,
        "session_id": sess.session_id, "source_path": "%s-transcripts/%s" % (sess.runtime, Path(sess.path).name),
        "source_sha256": sess.prefix_sha256,
        "started_at": _iso_local(cfg, sess.started_at), "updated_at": _iso_local(cfg, last_at),
        "cwd": _rel_cwd(cfg, sess.cwd), "git_branch": sess.git_branch, "git_head": git_head,
        "entities": entity_ids, "external_context": bool(sess.external_context),
        "redactions": redact.total(counts), "speakers": sorted({e.speaker for e in humans if e.principal}),
        "turns": len([e for e in humans if e.principal]),
    }
    out = []
    for i, part in enumerate(parts, 1):
        rel = base if i == 1 else base[:-3] + "-%d.md" % i
        for e in part:
            e.ref = "brain/%s#%s" % (rel, e.label)
        title = "Session %s %s %s%s" % (meta["started_at"][:16].replace("T", " "), sess.runtime,
                                         sess.session_id[:8], "" if i == 1 else " (part %d)" % i)
        files = [_rel_file(cfg, f) for f in sess.files if not private_file(cfg, sess, f)] \
            if i == len(parts) else []
        m = dict(meta, part=i)
        full = frontmatter.dump(m, _body(sess, part, sess.last_ordinal, title, True, files), ORDER)
        if policy == "stub-only":
            stub = frontmatter.dump(dict(m, stub=True), _body(sess, part, sess.last_ordinal, title, False, files), ORDER)
            out.append((rel, stub, full))
        elif policy == "local":
            out.append((rel, "", full))
        else:
            out.append((rel, full, None))
    return out


def _rel_cwd(cfg: Config, cwd: str) -> str:
    """cwd relative to the instance root: no machine-local absolute path is committed."""
    if not cwd:
        return ""
    root, real = os.path.realpath(str(cfg.root)), os.path.realpath(cwd)
    if real == root:
        return "."
    if real.startswith(root + os.sep):
        return Path(os.path.relpath(real, root)).as_posix()
    return "(outside the instance)"


def _iso_local(cfg: Config, at: str) -> str:
    try:
        return iso(cfg.local(at))
    except (ValueError, TypeError):
        return ""


def cursors(cfg: Config) -> Dict[str, Dict]:
    return read_json(cfg.state / "cursors.json", {})


def update(cfg: Config, path: Path, parser, entity_names: Dict[str, str], trusted: bool = False):
    """Journal one transcript -> (session or None, entries new since the cursor, commit()).

    The caller persists what it derived from the new entries (inbox
    candidates) and only then calls commit() to advance the cursor, so a
    crash in between re-derives them next time instead of losing them.
    `trusted`: the transcript is the runtime's own log (sync vetted it), so every journaled line is
    attested (provenance.py); a hand-written note never is.
    """
    noop = (None, [], lambda: None)
    if cfg.journal_policy == "off":
        return noop
    key = "%s" % os.path.realpath(str(path))
    cur = cursors(cfg).get(key) or {}
    through = int(cur.get("through") or 0)
    n = count_lines(path)
    revived = _revived(cfg, cur)
    if n <= through and not revived:
        return noop
    sess = parser(path, upto=n)
    if not getattr(sess, "automation", "") and sess.runtime in ("claude", "codex"):
        from . import provenance
        if provenance.automation_session(cfg, sess.runtime, sess.session_id, str(path)):
            to_automation(sess, "a capture hook saw this session started by automation")
    built = build_entries(cfg, sess, sticky=bool(cur.get("private")))
    entries = built[0]
    if not [e for e in entries if e.kind == "msg"]:
        return None, [], lambda: _save_cursor(cfg, key, sess, "", entries)
    rel0 = base_relpath(cfg, sess)
    if not cur:
        through = lookup.marker_through(cfg, rel0)
    ents = sorted({eid for e in entries if e.kind == "msg" and e.principal
                   for eid, name in entity_names.items() if cues.mentions(e.text, name)})
    head = lookup.existing_head(cfg, rel0) or gitutil.head(cfg.root)
    rendered = render(cfg, sess, ents, head, built)
    for rel, public, local in rendered:
        if public:
            write_text_if_changed(cfg.brain / rel, public)
        if local is not None:
            cfg.ensure_state()
            write_text_if_changed(cfg.state / rel, local)
    if trusted:
        from . import provenance
        provenance.attest_journal(cfg, sess, [(rel, [e for e in entries if e.ref.partition("#")[0] == "brain/" + rel])
                                              for rel, _, _ in rendered])
    new = [e for e in entries if e.ordinal > through or e.ordinal in revived]
    return sess, new, lambda: _save_cursor(cfg, key, sess, rel0, entries)


def _revived(cfg: Config, cur: Dict) -> set:
    """Ordinals omitted as non-principal last time whose speaker now resolves (for
    example after git user.email is fixed): re-journaled instead of lost."""
    out = set()
    for ordinal, raw in cur.get("omitted") or []:
        slug = cfg.resolve_speaker(str(raw))
        if slug and cfg.consents(slug):
            out.add(int(ordinal))
    return out


def _save_cursor(cfg: Config, key: str, sess: Session, rel: str, entries: List[Entry]) -> None:
    cfg.ensure_state()
    data = cursors(cfg)
    data[key] = {"through": sess.last_ordinal, "session_id": sess.session_id, "runtime": sess.runtime,
                 "journal": ("brain/" + rel) if rel else "",
                 "private": bool((data.get(key) or {}).get("private")) or private_read(cfg, sess),
                 "omitted": [[e.ordinal, e.speaker] for e in entries if e.kind == "msg" and not e.principal]}
    write_json(cfg.state / "cursors.json", data)
