"""v1.0 learning loop, GPT-6 review round 2 (2026-09-29): R5, R6, R7.

Threat model: anyone who can write files in the instance repo (a prompt-injected
agent, a planted document, a collaborator's commit) must not be able to forge the
operator's words, replay or roll back a confirmation, or pull another project's
conversations into this brain. Every test here failed on release/v1.0 @ 8b2987d.

R5  evidence state lives OUTSIDE the repo (extstate.py): deleting a journal line
    together with its attestation, rolling a consumed confirmation back, or copying
    another project's evidence all leave the evidence unverified.
R6  brain.json capture.also_cwd (repo-writable) no longer widens the transcript
    roots; extra roots come only from `tessbrain.py roots add` at a real terminal.
R7  a confirmation is a narrow directive ("confirm <id>"), never a question,
    quote, condition, hypothetical or negation.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib
from test_brain_provenance_adversarial import SID, _cli, _material, _meta, _say

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "brain"))
from brainlib import confirm  # noqa: E402


def _review(inst, rid):
    rc, items = _cli(inst, "review")
    assert rc == 0, items
    return next(it for it in items if it["id"] == rid)


def _strip_repo_rows(inst, pred):
    """What a repo writer can do to any evidence kept in the repo: drop rows from every jsonl in local state."""
    for p in (inst / ".tess").rglob("*.jsonl"):
        keep = [l for l in p.read_text().splitlines(True) if not (l.strip() and pred(json.loads(l)))]
        p.write_text("".join(keep))


# R5 ---------------------------------------------------------------------------------------------------

def test_r5_deleting_a_later_line_and_its_attestation_leaves_the_file_unverified(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    _review(inst, rid)
    _say(inst, cdir, path, "confirm %s" % rid)
    _say(inst, cdir, path, "no, wait. The shoot budget is not settled yet.")
    jfile = Path(fxlib.journal_of(inst, SID))
    raw = jfile.read_text()
    doubt = next(l for l in raw.splitlines() if "no, wait" in l)
    label = re.search(r"\b(L\d+)\b", doubt).group(1)
    jfile.write_text(raw.replace(doubt + "\n", ""))
    _strip_repo_rows(inst, lambda r: str(r.get("ref") or r.get("row", {}).get("ref") or "").endswith("#" + label))
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
    assert rc == 1 and _meta(rec)["status"] == "proposed", out


def test_r5_a_consumed_confirmation_cannot_be_rolled_back_and_replayed(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    _review(inst, rid)
    _say(inst, cdir, path, "confirm %s" % rid)
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
    assert rc == 0 and out["status"] == "accepted", out
    # the attacker flips the record back, lets it be shown again, then removes that newer presentation and the
    # `used` mark so the operator's old words look fresh and unused again
    rec.write_text(rec.read_text().replace('status: "accepted"', 'status: "proposed"', 1))
    time.sleep(1.1)
    _review(inst, rid)
    rows = [json.loads(l) for p in (inst / ".tess").rglob("*.jsonl") for l in p.read_text().splitlines() if l]
    shown = [r for r in rows if r.get("t") == "shown" and r.get("id") == rid]
    newest = max((r.get("at") for r in shown), default=None)
    _strip_repo_rows(inst, lambda r: (r.get("t") == "used" and r.get("id") == rid)
                     or (r.get("t") == "shown" and r.get("id") == rid and r.get("at") == newest and len(shown) > 1))
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
    assert rc == 1 and _meta(rec)["status"] == "proposed", out


def test_r5_evidence_copied_from_another_project_is_refused(tmp_path):
    inst_a, cdir, path, rec, rid = _material(tmp_path / "a")
    _review(inst_a, rid)
    _say(inst_a, cdir, path, "confirm %s" % rid)
    inst_b = Path(fxlib.make(str(tmp_path / "b" / "fx")))
    for sub in ("brain", ".tess"):
        shutil.rmtree(str(inst_b / sub), ignore_errors=True)
        shutil.copytree(str(inst_a / sub), str(inst_b / sub))
    rec_b = inst_b / rec.relative_to(inst_a)
    rc, out = _cli(inst_b, "confirm", rid, "--quote", "confirm %s" % rid)  # the repo copy alone
    assert rc == 1 and _meta(rec_b)["status"] == "proposed", out
    from brainlib import extstate
    from brainlib.config import Config
    a_dir, b_dir = extstate.project_dir(Config(inst_a)), extstate.project_dir(Config(inst_b))
    assert a_dir and b_dir and a_dir != b_dir
    for name in ("ledger.jsonl", "head.json"):  # even the out-of-repo ledger: every MAC names project A
        shutil.copy(str(a_dir / name), str(b_dir / name))
    rc, out = _cli(inst_b, "confirm", rid, "--quote", "confirm %s" % rid)
    assert rc == 1 and _meta(rec_b)["status"] == "proposed", out
    rc, out = _cli(inst_a, "confirm", rid, "--quote", "confirm %s" % rid)  # project A itself still works
    assert rc == 0 and out["status"] == "accepted", out


def test_r5_a_new_machine_with_no_external_state_is_review_only_not_an_error(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    _review(inst, rid)
    _say(inst, cdir, path, "confirm %s" % rid)
    fresh = tmp_path / "other-machine-key"
    fresh.mkdir(mode=0o700)
    env = {"TESS_BRAIN_PROVENANCE_DIR": str(fresh)}
    r = fxlib.cli(inst, "--json", "confirm", rid, "--quote", "confirm %s" % rid, env=env)
    assert r.returncode == 1 and "Traceback" not in r.stderr, r.stdout + r.stderr
    assert _meta(rec)["status"] == "proposed"
    assert fxlib.cli(inst, "--json", "review", env=env).returncode == 0


def _pdir(inst):
    from brainlib import extstate
    from brainlib.config import Config
    return extstate.project_dir(Config(inst))


def test_r5_a_sandboxed_shell_queues_signed_rows_and_the_next_hook_moves_them(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    d = _pdir(inst)
    files = [f for f in d.iterdir() if f.is_file()]
    for f in files + [d]:  # what the Codex sandbox leaves the agent's shell: read-only
        os.chmod(str(f), 0o500 if f == d else 0o400)
    try:
        _review(inst, rid)
        box = inst / ".tess/state/brain/outbox.jsonl"
        assert box.is_file() and rid in box.read_text()
    finally:
        for f in files + [d]:
            os.chmod(str(f), 0o700 if f == d else 0o600)
    _say(inst, cdir, path, "confirm %s" % rid)  # sync (as the hook-spawned one does) drains the outbox first
    assert not box.exists() and rid in (d / "ledger.jsonl").read_text()
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
    assert rc == 0 and out["status"] == "accepted", out


def test_r5_a_truncated_external_ledger_is_a_rollback_and_verifies_nothing(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    _review(inst, rid)
    _say(inst, cdir, path, "confirm %s" % rid)
    led = _pdir(inst) / "ledger.jsonl"
    lines = led.read_text().splitlines(True)
    led.write_text("".join(lines[:-1]))
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % rid)
    assert rc == 1 and _meta(rec)["status"] == "proposed", out
    assert "rolled back" in (inst / ".tess/state/brain/errors.log").read_text()


# R6 ---------------------------------------------------------------------------------------------------

def _codex_journals(inst):
    return [p for p in (inst / "brain" / "journal").rglob("*.md") if 'runtime: "codex"' in p.read_text()] \
        if (inst / "brain" / "journal").is_dir() else []


def _brain_json_with(tmp_path, also):
    data = json.loads(Path(fxlib.HERE, "brain.json").read_text())
    data["capture"]["also_cwd"] = also
    p = tmp_path / "brain.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_r6_repo_also_cwd_slash_pulls_in_no_foreign_transcripts(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx"), brain_json=_brain_json_with(tmp_path, ["/"])))
    none = str(inst / ".no-such-home")
    r = fxlib.cli(inst, "sync", "--claude-dir", none, "--codex-home", fxlib.CODEX_HOME, "--gemini-home", none)
    assert r.returncode in (0, 3), r.stdout + r.stderr
    assert _codex_journals(inst) == []
    r = fxlib.cli(inst, "sync", "--codex-home", fxlib.CODEX_HOME, "--also-cwd", "/")  # nor from the command line
    assert r.returncode != 0 and _codex_journals(inst) == []


def _tty(inst, args, answer, home):
    """Run tessbrain.py with a real pseudo-terminal on stdin/stdout, typing `answer`."""
    import pty
    master, slave = pty.openpty()
    env = dict(os.environ, HOME=str(home))
    p = subprocess.Popen([sys.executable, fxlib.TESSBRAIN, "--root", str(inst)] + list(args),
                         stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True)
    os.close(slave)
    os.write(master, (answer + "\n").encode())
    out = b""
    while True:
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    p.wait(timeout=60)
    os.close(master)
    return p.returncode, out.decode(errors="replace")


def _moved_codex_home(tmp_path, old_repo):
    """The fixture's Codex rollouts, as if they ran in `old_repo` (an earlier path of this instance)."""
    home = tmp_path / "codexhome"
    shutil.copytree(fxlib.CODEX_HOME, str(home))
    for p in home.rglob("*.jsonl"):
        p.write_text(p.read_text().replace(fxlib.CODEX_CWD, str(old_repo)))
    return str(home)


def test_r6_a_root_added_at_a_real_terminal_is_honoured_and_bad_roots_are_refused(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    home = tmp_path.resolve()
    old = home / "old-place" / "fx"
    codex_home = _moved_codex_home(tmp_path, old)
    none = str(inst / ".no-such-home")
    sync = ["sync", "--claude-dir", none, "--codex-home", codex_home, "--gemini-home", none]
    assert fxlib.cli(inst, *sync).returncode in (0, 3) and _codex_journals(inst) == []  # not ours by default
    r = fxlib.cli(inst, "roots", "add", str(old), stdin="yes\n", env={"HOME": str(home)})
    assert r.returncode != 0 and "terminal" in (r.stdout + r.stderr)  # piped stdin: not the operator
    other = home / "other-client"
    fxlib.make(str(other), git=False)
    for bad in ("/", str(home), "/usr", str(inst.parent), str(other), "old-place/fx"):
        rc, out = _tty(inst, ["roots", "add", bad], "yes", home)
        assert rc != 0 and "refused" in out, (bad, out)
    rc, out = _tty(inst, ["roots", "add", str(old)], "no", home)
    assert rc != 0
    assert str(old) not in fxlib.cli(inst, "--json", "roots", "list").stdout
    rc, out = _tty(inst, ["roots", "add", str(old)], "yes", home)
    assert rc == 0 and "journaled" in out, out
    assert fxlib.cli(inst, *sync).returncode in (0, 3)
    assert _codex_journals(inst), "the operator's own extra root must be honoured"


# R7 ---------------------------------------------------------------------------------------------------

RID, ALIAS = "D-20260929-1412-pricing", "D-0929-pricing"

REFUSED = [
    "Should I confirm D-0929-pricing?",
    "confirm D-0929-pricing?",
    "Confirm D-0929-pricing only after legal approval",
    "confirm D-0929-pricing if legal approves",
    "I'll confirm D-0929-pricing once the budget is final",
    "confirm D-0929-pricing unless finance objects",
    "confirm D-0929-pricing pending review",
    "confirm D-0929-pricing when the client signs",
    "would you confirm D-0929-pricing",
    "we could confirm D-0929-pricing",
    "maybe confirm D-0929-pricing",
    "don't confirm D-0929-pricing",
    "never confirm D-0929-pricing",
    'He said "confirm D-0929-pricing"',
    # v1.0.0 item b: the exact reply wrapped in quotes is now a confirmation (users copy the shown
    # phrase with its quotes); a quote inside a longer sentence, above, still is not.
    "> confirm D-0929-pricing",
    "confirm D-0929-pricing and D-0929-other",
    "confirm D-0929-pricing\nactually wait, not yet",
    # round 3: the WHOLE message must be the directive; a lead-in line no longer passes
    "Looks right to me.\nconfirm D-0929-pricing",
]
ACCEPTED = [
    "confirm D-0929-pricing",
    "Confirm D-0929-pricing.",
    "CONFIRM d-0929-pricing",
    "yes, confirm D-0929-pricing",
    "Yes confirm D-0929-pricing please",
    "confirm D-0929-pricing please.",
    "accept D-0929-pricing",
    "confirm D-20260929-1412-pricing",
    '"confirm D-0929-pricing"',
]


@pytest.mark.parametrize("text", REFUSED)
def test_r7_loose_or_conditional_words_do_not_confirm(text):
    assert confirm.intent(text, RID, "confirm", ALIAS) != "", text


@pytest.mark.parametrize("text", ACCEPTED)
def test_r7_the_narrow_directive_confirms(text):
    assert confirm.intent(text, RID, "confirm", ALIAS) == "", text


@pytest.mark.parametrize("text,ok", [
    ("reject D-0929-pricing", True), ("retract D-0929-pricing, that one was not a decision", True),
    ("Reject D-0929-pricing: wrong number.", True), ("Should I reject D-0929-pricing?", False),
    ("reject D-0929-pricing if the client objects", False), ("confirm D-0929-pricing", False),
])
def test_r7_rejections_follow_the_same_grammar(text, ok):
    assert (confirm.intent(text, RID, "reject", ALIAS) == "") is ok, text


def test_r7_a_question_reply_does_not_confirm_end_to_end(tmp_path):
    inst, cdir, path, rec, rid = _material(tmp_path)
    short = _review(inst, rid)["short_id"]
    for said in ("Should I confirm %s?" % short, "Confirm %s only after legal approval" % short):
        _say(inst, cdir, path, said)
        rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % short)
        assert rc == 1 and _meta(rec)["status"] == "proposed", (said, out)
    _say(inst, cdir, path, "confirm %s" % short)
    rc, out = _cli(inst, "confirm", rid, "--quote", "confirm %s" % short)
    assert rc == 0 and out["status"] == "accepted", out
