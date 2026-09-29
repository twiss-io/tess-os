"""Provenance: which operator words the brain may treat as REAL evidence.

Codex security review of v1.0.0 (2026-09-29): every file under the instance
repo (journal notes, turns.jsonl, sessions.json, inbox candidates) can be
written by a planted document, a pulled commit or a prompt-injected agent. A
journal-shaped line `[L1 10:00 <operator> cli] ...` in such a file was taken
as the operator's own words. Evidence is now authenticated:

* Trusted transcripts are the runtime's own session logs: a regular file
  OUTSIDE the instance, owned by this user, not group/world-writable, whose
  recorded cwd is inside the instance (transcript_ok).
* When the journal writes lines from a trusted transcript it appends an
  attestation per line: HMAC-SHA256 over (ref, kind, speaker, text, time)
  under a per-machine key kept OUTSIDE the repo (~/.config/tess/brain/key,
  0600; created by the SessionStart hook, since a sandboxed agent shell may
  read but not write there). Nothing in the repo can mint one.
* A journal line is trusted only when its own attestation verifies AND its
  file is intact: every attested line of that file is present unchanged and
  no unattested line was added (so a deleted "no wait" cannot settle a
  decision). Turns captured by the UserPromptSubmit hook carry the same MAC.
* Unverified evidence never produces an accepted record (verify V13).

Residual, stated plainly: code running as this user OUTSIDE any sandbox can
read the key, like it can read anything else the operator can. The defence
is against repo-level writers, not a compromised account.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import Config, log_error
from .textutil import normalize

KEY_ENV = "TESS_BRAIN_PROVENANCE_DIR"
STORE = "provenance.jsonl"
_KEYS: Dict[str, bytes] = {}
_STORE_CACHE: Dict[str, Tuple[int, int, Dict]] = {}


def key_dir() -> Path:
    env = os.environ.get(KEY_ENV)
    if env:
        return Path(env)
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "tess" / "brain"


def _inside(child: str, parent: str) -> bool:
    c, p = os.path.realpath(child), os.path.realpath(parent)
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def _owned_private(path: Path, mask: int) -> str:
    st = os.stat(str(path))
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        return "%s is not owned by this user" % path
    if st.st_mode & mask:
        return "%s is accessible to other users (mode %o)" % (path, stat.S_IMODE(st.st_mode))
    return ""


def key(cfg: Config) -> Optional[bytes]:
    """The per-machine key (created on first use), or None (fail closed: nothing is attested)."""
    d = key_dir()
    if _inside(str(d), str(cfg.root)):
        log_error(cfg, "provenance: key dir %s is inside the instance; refusing it" % d)
        return None
    p = d / "key"
    cached = _KEYS.get(str(p))
    if cached:
        return cached
    try:
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not p.exists():
            fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(secrets.token_bytes(32))
        why = _owned_private(d, 0o022) or _owned_private(p, 0o077)
        if why:
            log_error(cfg, "provenance: unsafe key: " + why)
            return None
        data = p.read_bytes()
    except OSError as exc:
        log_error(cfg, "provenance: key unavailable at %s" % p, exc)
        return None
    if len(data) < 32:
        log_error(cfg, "provenance: key at %s is too short" % p)
        return None
    _KEYS[str(p)] = data
    return data


def mac(cfg: Config, *parts: str) -> str:
    k = key(cfg)
    if k is None:
        return ""
    msg = "\x1f".join(str(x) for x in parts).encode("utf-8")
    return hmac.new(k, msg, hashlib.sha256).hexdigest()


def _eq(cfg: Config, got: str, *parts: str) -> bool:
    want = mac(cfg, *parts)
    return bool(want) and bool(got) and hmac.compare_digest(str(got), want)


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize(text or "").encode("utf-8")).hexdigest()


# -- trusted transcripts ------------------------------------------------------------------------------

def transcript_ok(cfg: Config, path: Path, cwd: Optional[str], cwds: List[str],
                  store: Optional[List[Path]] = None) -> str:
    """'' when `path` may be journaled as this instance's runtime transcript, else the reason.

    The same check for discovered, hook-reported (sessions.json) and --transcript paths."""
    try:
        real = os.path.realpath(str(path))
        if not os.path.isfile(real):
            return "not a regular file"
        if _inside(real, str(cfg.root)):
            return "inside the instance (a repo file, not a runtime transcript)"
        why = _owned_private(Path(real), 0o022)
        if why:
            return why
    except OSError as exc:
        return "unreadable (%s)" % exc
    if store is not None and not any(_inside(real, str(s)) for s in store):
        return "outside the runtime's transcript store"
    roots = [str(cfg.root)] + list(cwds)
    if not cwd or not any(_inside(cwd, r) for r in roots):
        return "its session cwd %r is not inside this instance" % (cwd or "")
    return ""


# -- the attestation store (append-only, local state) -------------------------------------------------

def _store_path(cfg: Config) -> Path:
    return cfg.state / STORE


def _append(cfg: Config, rows: List[Dict]) -> None:
    if not rows:
        return
    cfg.ensure_state()
    with open(_store_path(cfg), "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def _load(cfg: Config) -> Dict:
    """{'lines': {ref: row}, 'files': {path: set(refs)}, 'sessions': {path: row}, 'shown': {id: row},
    'used': set(refs)}; rows whose MAC does not verify are ignored."""
    p = _store_path(cfg)
    try:
        st = p.stat()
    except OSError:
        return {"lines": {}, "files": {}, "sessions": {}, "shown": {}, "used": set()}
    hit = _STORE_CACHE.get(str(p))
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    out: Dict = {"lines": {}, "files": {}, "sessions": {}, "shown": {}, "used": set()}
    with open(p, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            try:
                r = json.loads(raw)
            except ValueError:
                continue
            if isinstance(r, dict):
                _ingest(cfg, out, r)
    _STORE_CACHE[str(p)] = (st.st_mtime_ns, st.st_size, out)
    return out


def _ingest(cfg: Config, out: Dict, r: Dict) -> None:
    t = r.get("t")
    if t == "line" and _eq(cfg, r.get("mac"), "line", r.get("ref"), r.get("kind"), r.get("speaker"),
                           r.get("h"), r.get("at")):
        out["lines"][r["ref"]] = r
        out["files"].setdefault(str(r["ref"]).partition("#")[0], set()).add(r["ref"])
    elif t == "session" and _eq(cfg, r.get("mac"), "session", r.get("path"), r.get("sid"), r.get("runtime"),
                                "1" if r.get("external") else "0"):
        out["sessions"][r["path"]] = r
    elif t == "shown" and _eq(cfg, r.get("mac"), "shown", r.get("id"), r.get("h"), r.get("at"), r.get("sid") or ""):
        out["shown"][r["id"]] = r
    elif t == "used" and _eq(cfg, r.get("mac"), "used", r.get("ref"), r.get("id")):
        out["used"].add("%s|%s" % (r["ref"], r["id"]))


def attest_journal(cfg: Config, sess, rendered: List[Tuple[str, List]]) -> None:
    """Attest every line of a session just written from a TRUSTED transcript (journal.update)."""
    have = _load(cfg)
    rows: List[Dict] = []
    for rel, entries in rendered:
        path = "brain/" + rel
        ext = bool(sess.external_context)
        cur = have["sessions"].get(path)
        if cur is None or bool(cur.get("external")) != ext:
            rows.append({"t": "session", "path": path, "sid": sess.session_id, "runtime": sess.runtime,
                         "external": ext, "mac": mac(cfg, "session", path, sess.session_id, sess.runtime,
                                                     "1" if ext else "0")})
        for e in entries:
            h = text_hash(e.text)
            old = have["lines"].get(e.ref)
            if old and old.get("h") == h and old.get("speaker") == e.speaker:
                continue
            rows.append({"t": "line", "ref": e.ref, "kind": e.kind, "speaker": e.speaker, "h": h, "at": e.at or "",
                         "mac": mac(cfg, "line", e.ref, e.kind, e.speaker, h, e.at or "")})
    if rows and not rows[0]["mac"]:
        return  # no key: nothing is attested (fail closed)
    _append(cfg, rows)


def _file_intact(cfg: Config, ref_path: str, lines: List) -> bool:
    st = _load(cfg)
    attested = st["files"].get(ref_path) or set()
    if not attested:
        return False
    present = {}
    for l in lines:
        present[l.ref] = l
    if set(present) != attested:
        return False
    for ref, l in present.items():
        row = st["lines"][ref]
        if row.get("kind") != l.kind or row.get("speaker") != l.speaker or row.get("h") != text_hash(l.text):
            return False
    return True


def line_trusted(cfg: Config, line) -> bool:
    """A journal line whose words and whole session file verify against the attestations."""
    if line is None or line.kind == "turn":
        return False
    from . import lookup
    return _file_intact(cfg, line.path, lookup.lines_for(cfg, line.path))


def line_at(cfg: Config, line) -> str:
    row = _load(cfg)["lines"].get(line.ref) if line is not None else None
    return str((row or {}).get("at") or "")


def session_of(cfg: Config, ref_path: str) -> Optional[Dict]:
    """The attested session row of a journal file (runtime, sid, external) or None."""
    return _load(cfg)["sessions"].get(ref_path)


# -- turns (UserPromptSubmit capture) ------------------------------------------------------------------

def turn_mac(cfg: Config, rec: Dict) -> str:
    return mac(cfg, "turn", rec.get("n"), rec.get("session"), rec.get("runtime"), rec.get("at"), rec.get("speaker"),
               "1" if rec.get("principal") else "0", text_hash(str(rec.get("text") or "")))


def turn_ok(cfg: Config, rec: Optional[Dict]) -> bool:
    if not rec:
        return False
    got = str(rec.get("mac") or "")
    want = turn_mac(cfg, rec)
    return bool(got) and bool(want) and hmac.compare_digest(got, want)


# -- presentation and confirmation --------------------------------------------------------------------

def shown(cfg: Config, item_id: str, h: str, at: str, sid: str) -> None:
    _append(cfg, [{"t": "shown", "id": item_id, "h": h, "at": at, "sid": sid,
                   "mac": mac(cfg, "shown", item_id, h, at, sid)}])


def last_shown(cfg: Config, item_id: str) -> Optional[Dict]:
    return _load(cfg)["shown"].get(item_id)


def used(cfg: Config, ref: str, item_id: str) -> bool:
    return "%s|%s" % (ref, item_id) in _load(cfg)["used"]


def consume(cfg: Config, ref: str, item_id: str) -> None:
    _append(cfg, [{"t": "used", "ref": ref, "id": item_id, "mac": mac(cfg, "used", ref, item_id)}])
