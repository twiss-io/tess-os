"""Onboarding state machine, answers and the session-start hook (spec 6.2-6.4, 9.1, 9.6).

Every assertion runs the real CLI (scripts/brain/onboard.py) with the test's
own interpreter in a throwaway instance: status transitions, verbatim-quote
enforcement, resume at the saved step, defer/skip, the source-repo guard,
and the hook's silent / pending / restore / nonce behaviour.
"""
from __future__ import annotations

import json
import time

import pytest

import _brain_oobe_helpers as h


def status(root):
    done = h.onboard(root, "status", "--json")
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def hook(root, **env):
    return h.onboard(root, "hook", "session-start", "--runtime", "claude", stdin="{}", extra_env=env)


def test_fresh_instance_is_pending_step_1_with_question(tmp_path):
    root = h.mini_instance(tmp_path)
    st = status(root)
    assert st["status"] == "pending" and st["step"] == 1 and st["total"] == 7
    assert "Who is this brain for?" in st["next_question"]
    assert not (root / "brain").exists(), "status must never write"


def test_answer_requires_verbatim_quote(tmp_path):
    root = h.mini_instance(tmp_path)
    done = h.onboard(root, "answer", "--step", "1", "--field", "mode", "--value", "agency")
    assert done.returncode == 2 and "--quote is required" in done.stderr
    assert not (root / "brain" / "brain.json").exists()


def test_answer_rejects_field_from_another_step_and_unknown_values(tmp_path):
    root = h.mini_instance(tmp_path)
    wrong = h.onboard(root, "answer", "--step", "2", "--field", "mode", "--value", "agency", "--quote", "x y")
    assert wrong.returncode == 2 and "belongs to step 1" in wrong.stderr
    bad = h.onboard(root, "answer", "--field", "mode", "--value", "robot", "--quote", "a robot brain")
    assert bad.returncode == 2 and "unknown mode" in bad.stderr


def test_first_answer_creates_brain_json_in_progress_and_keeps_quote(tmp_path):
    root = h.mini_instance(tmp_path)
    quote = "An agency, and my personal stuff too."
    done = h.onboard(root, "answer", "mode", "--value", "agency, personal", "--quote", quote,
                     "--runtime", "claude-code", "--session", "s1")
    assert done.returncode == 0, done.stderr
    brain = json.loads((root / "brain" / "brain.json").read_text())
    assert brain["kind"] == "tess-brain" and brain["schema"] == 1
    entry = brain["onboarding"]["answers"]["mode"]
    assert entry["value"] == ["agency", "personal"] and entry["quote"] == quote
    assert entry["verified"] is False and entry["runtime"] == "claude-code"
    assert brain["modes"] == ["agency", "personal"] and brain["primary_mode"] == "agency"
    st = status(root)
    assert st["status"] == "in_progress" and st["step"] == 2


def test_until_step_resumes_at_saved_step_and_apply_refuses(tmp_path):
    root = h.mini_instance(tmp_path)
    fx = str(h.FIXTURES / "answers-agency-solo.json")
    assert h.onboard(root, "init", "--non-interactive", "--answers", fx, "--until-step", "3").returncode == 0
    st = status(root)
    assert st["status"] == "in_progress" and st["step"] == 4 and st["missing"] == ["principals"]
    assert h.onboard(root, "apply").returncode == 3
    assert h.onboard(root, "init", "--non-interactive", "--answers", fx).returncode == 0
    assert status(root)["ready_to_apply"] is True


def test_non_interactive_defaults_need_an_operator_name(tmp_path):
    root = h.mini_instance(tmp_path, profile={})
    done = h.onboard(root, "init", "--mode", "personal", "--non-interactive")
    assert done.returncode == 2 and "--operator" in done.stderr
    ok = h.onboard(root, "init", "--mode", "personal", "--operator", "Ada", "--non-interactive")
    assert ok.returncode == 0 and status(root)["ready_to_apply"] is True
    ans = json.loads((root / "brain" / "brain.json").read_text())["onboarding"]["answers"]
    assert ans["mode"]["quote"] == "--mode personal" and ans["mode"]["runtime"] == "cli"
    assert ans["journal"]["runtime"] == "default" and ans["journal"]["quote"] == ""


def test_preset_must_match_mode(tmp_path):
    root = h.mini_instance(tmp_path)
    h.onboard(root, "answer", "mode", "--value", "personal", "--quote", "just me")
    done = h.onboard(root, "answer", "preset", "--value", "startup", "--quote", "startup please")
    assert done.returncode == 2 and "needs mode organisation" in done.stderr


def test_defer_then_due_becomes_pending_again(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard(root, "defer", "--days", "7").returncode == 0
    assert status(root)["status"] == "deferred"
    assert hook(root).stdout == "", "deferred before remind_after is silent"
    path = root / "brain" / "brain.json"
    brain = json.loads(path.read_text())
    brain["onboarding"]["remind_after"] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(brain))
    assert status(root)["status"] == "pending"
    assert "ONBOARDING PENDING" in hook(root).stdout


def test_source_repo_is_silent_and_refuses(tmp_path):
    root = h.mini_instance(tmp_path, source_repo=True)
    assert status(root)["status"] == "source-repo"
    assert hook(root).stdout == ""
    assert h.onboard(root, "apply").returncode == 3
    assert h.onboard(root, "answer", "mode", "--value", "agency", "--quote", "agency").returncode == 3


def test_hook_pending_json_shape_nonce_and_speed(tmp_path):
    root = h.mini_instance(tmp_path)
    start = time.monotonic()
    done = hook(root, TESS_BRAIN_TEST_NONCE="OOBE-NONCE-T1")
    elapsed = time.monotonic() - start
    assert done.returncode == 0 and elapsed < 2.0
    out = json.loads(done.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert ctx.startswith("ONBOARDING PENDING (step 1/7): greet the operator as Tess")
    assert "Who is this brain for?" in ctx and "OOBE-NONCE-T1" in ctx
    assert len(done.stdout.encode()) <= 4096


@pytest.mark.parametrize("var", ["TESS_BRAIN_QUIET", "TESS_HEADLESS"])
def test_hook_quiet_env_is_silent(tmp_path, var):
    root = h.mini_instance(tmp_path)
    done = hook(root, **{var: "1"})
    assert done.returncode == 0 and done.stdout == ""


def test_hook_never_fails_on_corrupt_brain_json(tmp_path):
    root = h.mini_instance(tmp_path)
    (root / "brain").mkdir()
    (root / "brain" / "brain.json").write_text("{not json")
    done = hook(root)
    assert done.returncode == 0 and done.stdout == ""
    log = root / ".tess" / "state" / "brain" / "errors.log"
    assert "not valid JSON" in log.read_text()
    assert (root / ".tess" / "state" / "brain" / ".gitignore").read_text() == "*\n"


def test_completed_instance_hook_silent_until_profile_missing(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "personal").returncode == 0
    assert status(root)["status"] == "complete"
    assert hook(root).stdout == "", "complete + profile present: no onboarding text"
    (root / "operator" / "profile.json").unlink()
    ctx = json.loads(hook(root).stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.startswith("BRAIN RESTORE NEEDED") and "ONBOARDING" not in ctx
    assert h.onboard(root, "restore").returncode == 0
    prof = json.loads((root / "operator" / "profile.json").read_text())
    assert prof["operator_name"] == "Rowan Vale" and prof["assistant_name"] == "Tess"
    assert hook(root).stdout == ""


def test_skip_records_personal_layer_and_is_final(tmp_path):
    root = h.mini_instance(tmp_path)
    done = h.onboard(root, "skip", "--quote", "skip onboarding for now")
    assert done.returncode == 0, done.stderr
    assert status(root)["status"] == "skipped"
    assert (root / "brain" / "life" / "AGENTS.md").exists()
    assert hook(root).stdout == ""
    again = h.onboard(root, "answer", "mode", "--value", "agency", "--quote", "agency")
    assert again.returncode == 3
