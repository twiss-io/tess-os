"""CI usage plan: the macOS legs are tiered, no required check ever is.

Covers .github/scripts/ci_plan.py (the decision) and the shape of
.github/workflows/ci.yml that makes the decision safe: required checks are
never skipped, never wait on the plan job, and a failed plan runs macOS.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".github" / "scripts" / "ci_plan.py"
CI = REPO / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="Tess OS source repo only (no CI plan here)")

# Status checks the ruleset on the default branch requires, by job name.
REQUIRED_JOBS = ("test", "create-tess", "secret-scan")


def _load():
    spec = importlib.util.spec_from_file_location("ci_plan", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plan = _load()


def _pr(changed, base="main", same_repo=True):
    return plan.decide("pull_request", "feature", base, same_repo, changed, None, "true")


# --- the change-to-check table (pull_request, cumulative diff) -----------------

@pytest.mark.parametrize("changed,expected", [
    (["docs/guide.md"], False),
    (["README.md", "CHANGELOG.md"], False),
    (["docs/img/a.png", "docs/x.md"], False),
    (["tests/test_x.py"], True),
    ([".tess/bin/tessctl"], True),
    ([".claude/hooks/tess-gate.py"], True),
    ([".tess/tess.lock"], True),
    (["requirements-dev.txt"], True),
    (["uv.lock"], True),
    (["create-tess/package.json"], True),
    (["create-tess/package-lock.json"], True),
    (["package.json"], True),
    (["create-tess/template/docs/readme.md"], True),
    ([".github/workflows/ci.yml"], True),
    ([".github/workflows/tess-gate.yml"], True),
    ([".github/scripts/ci_plan.py"], True),
    ([".github/CODEOWNERS"], True),
    (["core/policy/policy.yaml"], True),
    (["CLAUDE.md"], True),
    (["AGENTS.md"], True),
    (["some/unknown/path.bin"], True),
    (["docs/guide.md", "tests/test_x.py"], True),            # one non-doc path wins
    (["docs/guide.md", ".github/workflows/ci.yml"], True),   # protected path hidden among docs
    (["docs/run.py"], True),                                 # code under docs/ is not prose
    (["docs/../tessctl"], True),                             # traversal is never a docs path
    (["README.md.py"], True),
])
def test_pull_request_macos_decision(changed, expected):
    run, reason = _pr(changed)
    assert run is expected, reason


@pytest.mark.parametrize("changed", [None, []])
def test_uncomputable_or_empty_diff_runs_macos(changed):
    run, reason = _pr(changed)
    assert run is True and "failing closed" in reason


def test_fork_pull_request_runs_macos_even_if_docs_only():
    assert _pr(["docs/guide.md"], same_repo=False)[0] is True


def test_pull_request_into_integration_branch_defers_to_the_merge_push():
    assert _pr(["tests/test_x.py"], base="rc/v1.0.0")[0] is False
    assert _pr(["tests/test_x.py"], base="release/v1.0")[0] is False
    assert _pr(["docs/guide.md"], base="rc/v1.0.0")[0] is False
    # any other base (stacked feature branch) is judged by its diff
    assert _pr(["tests/test_x.py"], base="feature/other")[0] is True


# --- pushes ----------------------------------------------------------------

def _push(ref, open_pr=None, changed=None):
    return plan.decide("push", ref, "", True, changed, open_pr, "true")


def test_push_to_default_branch_always_runs_macos():
    assert _push("main", open_pr=True)[0] is True


@pytest.mark.parametrize("ref", ["rc/v1.0.0", "release/v1.0"])
def test_push_to_integration_branch(ref):
    assert _push(ref, open_pr=False)[0] is True      # no PR: this push owns macOS
    assert _push(ref, open_pr=None)[0] is True       # lookup failed: fail closed
    assert _push(ref, open_pr=True, changed=['docs/a.md'])[0] is False   # PR to main runs it for the same head


def test_push_to_feature_branch_skips_macos():
    assert _push("fix/anything", changed=["tests/test_x.py"])[0] is False


@pytest.mark.parametrize("ref", ["release", "rc", "releases/x", "xrelease/v1", "main2", "Main"])
def test_lookalike_branch_names_are_not_integration_branches(ref):
    assert plan.is_integration_branch(ref) is False


def test_dispatch_and_unknown_events():
    assert plan.decide("workflow_dispatch", "x", "", True, None, None, "true")[0] is True
    assert plan.decide("workflow_dispatch", "x", "", True, None, None, "")[0] is True
    assert plan.decide("workflow_dispatch", "x", "", True, None, None, "false")[0] is False
    assert plan.decide("merge_group", "x", "", True, None, None, "true")[0] is True
    assert plan.decide("", "", "", False, None, None, "")[0] is True


# --- diff computation against a real repository --------------------------------

def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
                               "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                               "HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1"}).stdout.strip()


def _commit(repo, name, text="x\n"):
    p = repo / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    _git(repo, "add", "--", name)
    _git(repo, "commit", "-q", "-m", "c " + name)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    return tmp_path


def test_cumulative_diff_uses_the_merge_base_not_the_last_commit(repo):
    base = _commit(repo, "a.txt")
    _git(repo, "checkout", "-q", "-b", "feat")
    _commit(repo, "tessctl")                    # protected path in an EARLIER commit
    head = _commit(repo, "docs/note.md")        # docs-only LAST commit
    assert sorted(plan.changed_files(base, head, str(repo))) == ["docs/note.md", "tessctl"]
    assert plan.docs_only(plan.changed_files(base, head, str(repo))) is False
    parent = _git(repo, "rev-parse", "HEAD~1")
    assert plan.docs_only(plan.changed_files(parent, head, str(repo))) is True   # last commit alone looks docs-only


def test_base_that_moved_on_does_not_pollute_the_diff(repo):
    root = _commit(repo, "a.txt")
    _git(repo, "checkout", "-q", "-b", "feat")
    head = _commit(repo, "docs/note.md")
    _git(repo, "checkout", "-q", "main")
    moved = _commit(repo, "tessctl")             # base advanced with a code change
    assert plan.changed_files(moved, head, str(repo)) == ["docs/note.md"]
    assert root


def test_rename_out_of_a_protected_path_reports_both_paths(repo):
    base = _commit(repo, ".tess/bin/tessctl", "echo\n")
    _git(repo, "checkout", "-q", "-b", "feat")
    (repo / "docs").mkdir()
    _git(repo, "mv", ".tess/bin/tessctl", "docs/tessctl.md")
    _git(repo, "commit", "-q", "-m", "mv")
    head = _git(repo, "rev-parse", "HEAD")
    files = plan.changed_files(base, head, str(repo))
    assert set(files) == {".tess/bin/tessctl", "docs/tessctl.md"}
    assert plan.docs_only(files) is False


@pytest.mark.parametrize("base,head", [("", ""), ("abc", "def"), ("0" * 40, "1" * 40), ("main", "HEAD")])
def test_uncomputable_diff_is_none(repo, base, head):
    _commit(repo, "a.txt")
    assert plan.changed_files(base, head, str(repo)) is None


# --- workflow shape: required checks stay unconditional ----------------------------

def _wf():
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def test_no_workflow_level_path_filters():
    on = _wf()[True] if True in _wf() else _wf()["on"]
    for trig in ("push", "pull_request"):
        cfg = on.get(trig) or {}
        assert "paths" not in cfg and "paths-ignore" not in cfg, trig


@pytest.mark.parametrize("job", REQUIRED_JOBS)
def test_required_jobs_are_unconditional_and_independent_of_the_plan(job):
    j = _wf()["jobs"][job]
    assert "if" not in j, job
    needs = j.get("needs") or []
    needs = [needs] if isinstance(needs, str) else needs
    assert "plan" not in needs, job
    assert j.get("continue-on-error") is not True, job


def test_required_job_names_are_unchanged():
    jobs = _wf()["jobs"]
    assert jobs["test"]["name"] == "tests (py${{ matrix.python-version }})"
    assert jobs["test"]["strategy"]["matrix"]["python-version"] == ["3.9", "3.12"]
    assert jobs["create-tess"]["name"].startswith("create-tess tests (node ${{ matrix.node-version }}")
    assert jobs["create-tess"]["strategy"]["matrix"]["node-version"] == ["18", "24"]
    assert jobs["secret-scan"]["name"] == "secret scan (gitleaks)"


MACOS_IF = "${{ !cancelled() && (needs.plan.result != 'success' || needs.plan.outputs.macos != 'false') }}"
CONFORMANCE_IF = "${{ !cancelled() && needs.test.result == 'success' }}"


def _fallback(expr):
    """(output name, JSON literal after `||`) of a `${{ fromJSON(needs.plan.outputs.X || '<json>') }}` matrix."""
    import json
    import re
    m = re.fullmatch(r"\$\{\{ fromJSON\(needs\.plan\.outputs\.(\w+) \|\| '(.*)'\) \}\}", expr.strip())
    assert m, expr
    return m.group(1), json.loads(m.group(2))


def _macos_if_runs(plan_result, macos_output):
    """Evaluate MACOS_IF's condition for a (plan.result, plan.outputs.macos) pair."""
    body = MACOS_IF[len("${{"):-len("}}")]
    body = body.replace("!cancelled()", "True").replace("&&", " and ").replace("||", " or ")
    body = body.replace("needs.plan.result", repr(plan_result)).replace("needs.plan.outputs.macos", repr(macos_output))
    return eval(body, {"__builtins__": {}})  # noqa: S307 - fixed expression from our own workflow file


def test_macos_legs_fail_closed_and_keep_the_full_matrix():
    jobs = _wf()["jobs"]
    assert jobs["macos"]["needs"] == "plan"
    assert jobs["macos"]["if"].strip() == MACOS_IF
    # truth table: only a successful plan that said macos=false skips the legs
    assert _macos_if_runs("success", "true") is True
    assert _macos_if_runs("success", "false") is False
    assert _macos_if_runs("success", "") is True            # plan ok, output missing: run
    for bad in ("failure", "cancelled", "skipped"):
        assert _macos_if_runs(bad, "") is True and _macos_if_runs(bad, "false") is True
    # the matrix comes from the plan; with no plan output both legs run
    name, fb = _fallback(jobs["macos"]["strategy"]["matrix"]["python-version"])
    assert name == "macos_pythons" and fb == ["3.9", "3.12"]
    conf = jobs["shell-conformance"]
    assert conf["if"].strip() == CONFORMANCE_IF
    name, fb = _fallback(conf["strategy"]["matrix"]["os"])
    assert name == "conformance_os" and fb == ["ubuntu-latest", "macos-latest"]
    assert sorted(conf["needs"]) == ["plan", "test"]


def test_every_job_has_a_timeout():
    for name, job in _wf()["jobs"].items():
        assert isinstance(job.get("timeout-minutes"), int) and job["timeout-minutes"] > 0, name


class _Ctx:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _eval_expr(expr, *, event, ref, run_id, pr=None):
    """Evaluate a GitHub `${{ }}` expression of the shapes used in the concurrency block."""
    import re
    parts = re.split(r"\$\{\{(.*?)\}\}", expr, flags=re.S)
    if len(parts) > 3:  # literal text between several ${{ }} segments
        return "".join(
            p if i % 2 == 0 else str(_eval_expr("${{" + p + "}}", event=event, ref=ref, run_id=run_id, pr=pr))
            for i, p in enumerate(parts)
        )
    body = " ".join(parts[1].split())
    body = body.replace("&&", " and ").replace("||", " or ").replace("!startsWith", "not startsWith")
    body = body.replace("github.event.pull_request.number", "github.pr")
    github = _Ctx(workflow="CI", event_name=event, ref=ref, run_id=run_id, pr=pr)
    return eval(  # noqa: S307 - fixed expression from our own workflow file
        body,
        {"__builtins__": {}},
        {
            "github": github,
            "format": lambda f, *a: f.format(*a),
            "startsWith": lambda a, b: a.startswith(b),
        },
    )


def _group(event, ref, run_id, pr=None):
    return _eval_expr(_wf()["concurrency"]["group"], event=event, ref=ref, run_id=run_id, pr=pr)


def _cancels(event, ref, run_id, pr=None):
    return _eval_expr(_wf()["concurrency"]["cancel-in-progress"], event=event, ref=ref, run_id=run_id, pr=pr)


def test_main_release_rc_and_dispatch_get_a_unique_group_per_run():
    cases = [
        ("push", "refs/heads/main"),
        ("push", "refs/heads/release/v1.2"),
        ("push", "refs/heads/rc/1.2.0"),
        ("workflow_dispatch", "refs/heads/main"),
        ("workflow_dispatch", "refs/heads/feature/x"),
    ]
    for event, ref in cases:
        g1, g2 = _group(event, ref, 111), _group(event, ref, 222)
        assert g1 != g2, (event, ref)
        assert "111" in g1 and "222" in g2
        assert not _cancels(event, ref, 111), (event, ref)


def test_pr_groups_include_the_pr_number_cancel_and_never_collide():
    a, a2, b = _group("pull_request", "refs/pull/7/merge", 1, 7), _group("pull_request", "refs/pull/7/merge", 2, 7), _group("pull_request", "refs/pull/8/merge", 3, 8)
    assert a == a2, "reruns/pushes of one PR share a group so the older one is cancelled"
    assert a != b, "two different PRs must never share a group"
    assert "7" in a and "8" in b
    assert _cancels("pull_request", "refs/pull/7/merge", 1, 7) is True


def test_push_triggers_only_main_release_and_rc_so_a_commit_is_not_run_twice():
    on = _wf()[True] if True in _wf() else _wf()["on"]
    assert on["push"] == {"branches": ["main", "rc/**", "release/**"]}
    assert "pull_request" in on and "workflow_dispatch" in on
    # a PR run is the only run that cancels; everything else gets its own group
    assert _cancels("pull_request", "refs/pull/7/merge", 1, 7) is True
    for event, ref in (("push", "refs/heads/main"), ("workflow_dispatch", "refs/heads/feat/a")):
        assert _cancels(event, ref, 1) is False
        assert _group(event, ref, 1) != _group("pull_request", "refs/pull/7/merge", 1, 7)


def test_plan_job_gets_only_read_permissions():
    perms = _wf()["jobs"]["plan"]["permissions"]
    assert perms == {"contents": "read", "pull-requests": "read"}


# --- gate-aware tiering (Quinn, macOS necessity, 2026-11-02) -----------------------------
# The macOS py3.9 leg caught the one Linux-invisible gate bypass; the py3.12 leg caught
# nothing the py3.9 leg and Linux did not. So: a gate/engine/conformance/pin change always
# runs py3.9 + conformance; py3.12 runs only at the doors of the default branch.

GATE_PATH_EXAMPLES = [
    ".claude/hooks/tess-gate.py",
    ".claude/hooks/run-pinned.py",
    ".claude/settings.json",
    ".tess/bin/tessctl",
    ".tess/core/pinned-scripts.sha256",
    ".tess/vendor/yaml/__init__.py",
    ".tess/tess.lock",
    "tessctl",
    "core/policy/policy.yaml",
    "requirements-dev.txt",
    ".github/ci-constraints.txt",
    "uv.lock",
    "pyproject.toml",
    "create-tess/package-lock.json",
    "tests/shell_conformance.py",
    "tests/test_v1_shell_conformance.py",
    "tests/gate_corpus_recorder.py",
    "tests/conftest.py",
    "tests/test_v1_b1_class.py",
    ".github/workflows/ci.yml",
    ".github/scripts/ci_plan.py",
    "tests/test_v1_round4_shell_model.py",
    "tests/test_v1_r6_gate_expand.py",
    "tests/test_v1_n1_n3.py",
    "scripts/brain/tessbrain.py",
    "core/contracts/policy.schema.json",
    "tess.manifest.json",
    # macOS file systems are case-insensitive: a case variant collides with the real file there
    ".CLAUDE/hooks/tess-gate.py",
    ".Claude/Settings.json",
    ".TESS/bin/tessctl",
    "Tests/Test_V1_B1_Class.py",
]

NON_GATE_EXAMPLES = ["docs/guide.md", "README.md", "agents/leah/README.md", "tests/test_memory_adopt.py"]


@pytest.mark.parametrize("path", GATE_PATH_EXAMPLES)
def test_gate_paths_are_recognised(path):
    assert plan.touches_gate([path]) is True
    assert plan.touches_gate(["docs/guide.md", path]) is True   # hidden among docs


@pytest.mark.parametrize("path", NON_GATE_EXAMPLES)
def test_other_paths_are_not_gate_paths(path):
    assert plan.touches_gate([path]) is False


def test_gate_patterns_are_case_insensitive_but_doc_patterns_are_not():
    assert plan.touches_gate([".CLAUDE/hooks/tess-gate.py"]) is True
    assert plan.is_docs_path("docs/guide.md") is True and plan.is_docs_path("DOCS/guide.md") is False


def test_odd_paths_count_as_gate_paths_and_empty_is_not():
    assert plan.touches_gate(["docs/../x"]) is True and plan.touches_gate(["/etc/x"]) is True
    assert plan.touches_gate([]) is False and plan.touches_gate(None) is False


@pytest.mark.parametrize("gate_path", GATE_PATH_EXAMPLES)
def test_gate_change_on_a_feature_push_runs_macos_py39_and_conformance(gate_path):
    run, reason = _push("fix/anything", changed=[gate_path, "docs/guide.md"])
    assert run is True and "gate" in reason


def test_docs_or_ordinary_change_on_a_feature_push_skips_macos():
    assert _push("fix/anything", changed=["docs/guide.md"])[0] is False
    assert _push("fix/anything", changed=["agents/leah/README.md"])[0] is False
    assert _push("fix/anything", changed=["tests/test_memory_adopt.py", "docs/a.md"])[0] is False


@pytest.mark.parametrize("changed", [None])
def test_uncomputable_diff_on_a_feature_push_runs_macos(changed):
    run, reason = _push("fix/anything", changed=changed)
    assert run is True and "failing closed" in reason


@pytest.mark.parametrize("base", ["rc/v1.0.0", "release/v1.0"])
def test_gate_change_in_a_pr_into_rc_or_release_runs_macos(base):
    assert _pr([".claude/hooks/tess-gate.py"], base=base)[0] is True
    assert _pr([".tess/bin/tessctl", "docs/a.md"], base=base)[0] is True
    assert _pr(["tests/shell_conformance.py"], base=base)[0] is True
    assert _pr(["docs/guide.md"], base=base)[0] is False
    assert _pr(["tests/test_memory_adopt.py"], base=base)[0] is False
    assert _pr(None, base=base)[0] is True and _pr([], base=base)[0] is True    # fail closed


@pytest.mark.parametrize("ref", ["rc/v1.0.0", "release/v1.0"])
def test_a_pr_owned_integration_push_still_runs_macos_for_a_gate_change(ref):
    # The PR's pull_request run may never start (merge conflict) or be superseded, so the gate
    # rule applies to PR-owned pushes too. Same inputs as the old test, which pinned the skip.
    run, reason = _push(ref, open_pr=True, changed=[".claude/hooks/tess-gate.py"])
    assert run is True and "gate" in reason
    assert _push(ref, open_pr=True, changed=["docs/a.md", "tests/shell_conformance.py"])[0] is True
    assert _push(ref, open_pr=True, changed=None)[0] is True        # diff uncomputable: fail closed


@pytest.mark.parametrize("ref", ["rc/v1.0.0", "release/v1.0"])
def test_a_pr_owned_integration_push_without_a_gate_change_skips_macos(ref):
    # negative: the PR run owns the legs when nothing the gate depends on changed
    assert _push(ref, open_pr=True, changed=["docs/a.md"])[0] is False
    assert _push(ref, open_pr=True, changed=["tests/test_memory_adopt.py"])[0] is False


def test_gate_change_in_a_dispatch_with_macos_false_still_skips():
    assert plan.decide("workflow_dispatch", "x", "", True, [".tess/bin/tessctl"], None, "false")[0] is False


def _full(event, ref="feature", base="", changed=None, open_pr=None, dispatch="true", same_repo=True):
    run, _ = plan.decide(event, ref, base, same_repo, changed, open_pr, dispatch)
    return plan.decide_full(event, ref, base, run, dispatch)


def test_py312_runs_on_a_pr_to_main_a_push_to_main_and_a_full_dispatch():
    assert _full("pull_request", base="main", changed=["tests/test_x.py"]) is True
    assert _full("pull_request", base="main", changed=["tests/test_x.py"], same_repo=False) is True
    assert _full("pull_request", base="main", changed=None) is True              # fail closed
    assert _full("push", ref="main") is True
    assert _full("workflow_dispatch", dispatch="true") is True
    assert _full("workflow_dispatch", dispatch="") is True


def test_py312_never_runs_on_rc_release_or_feature_paths():
    assert _full("push", ref="rc/v1.0.0", open_pr=False) is False                # rc push owns py3.9 only
    assert _full("push", ref="release/v1.0", open_pr=None) is False
    assert _full("push", ref="fix/x", changed=[".claude/hooks/tess-gate.py"]) is False
    assert _full("pull_request", base="rc/v1.0.0", changed=[".claude/hooks/tess-gate.py"]) is False
    assert _full("pull_request", base="release/v1.0", changed=[".tess/bin/tessctl"], same_repo=False) is False


def test_py312_skips_with_the_rest_when_macos_is_off():
    assert _full("pull_request", base="main", changed=["docs/guide.md"]) is False
    assert _full("workflow_dispatch", dispatch="false") is False
    assert plan.decide_full("pull_request", "x", "main", False, "true") is False


def test_py312_unknown_event_fails_closed():
    assert plan.decide_full("merge_group", "x", "", True, "true") is True


def test_main_writes_the_matrix_outputs(tmp_path, monkeypatch):
    out = tmp_path / "out"
    cases = [
        ({"EVENT_NAME": "push", "REF_NAME": "main"}, "true", '["3.9", "3.12"]'),
        ({"EVENT_NAME": "workflow_dispatch", "REF_NAME": "x", "DISPATCH_MACOS": "true"}, "true", '["3.9", "3.12"]'),
        ({"EVENT_NAME": "workflow_dispatch", "REF_NAME": "x", "DISPATCH_MACOS": "false"}, "false", '["3.9"]'),
    ]
    for env, macos, pythons in cases:
        out.write_text("")
        for k in ("EVENT_NAME", "REF_NAME", "DISPATCH_MACOS", "BASE_REF", "REPO", "HEAD_REPO", "PUSH_SHA"):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        assert plan.main() == 0
        lines = dict(l.split("=", 1) for l in out.read_text().splitlines())
        assert lines["macos"] == macos and lines["macos_pythons"] == pythons, env


def test_feature_push_computes_the_cumulative_diff_against_the_default_branch(repo, monkeypatch, tmp_path):
    base = _commit(repo, "a.txt")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    _git(repo, "checkout", "-q", "-b", "feat")
    _commit(repo, ".claude/hooks/tess-gate.py")        # gate change in an EARLIER commit
    head = _commit(repo, "docs/note.md")               # docs-only LAST commit
    assert plan.default_branch_sha(str(repo)) == base
    assert plan.touches_gate(plan.changed_files(base, head, str(repo))) is True
    out = tmp_path / "out"
    out.write_text("")
    for k, v in {"EVENT_NAME": "push", "REF_NAME": "feat", "PUSH_SHA": head, "GITHUB_OUTPUT": str(out)}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(repo)
    assert plan.main() == 0
    assert "macos=true" in out.read_text()


def test_feature_push_without_a_default_branch_ref_fails_closed(repo, monkeypatch, tmp_path):
    head = _commit(repo, "docs/note.md")
    out = tmp_path / "out"
    out.write_text("")
    for k, v in {"EVENT_NAME": "push", "REF_NAME": "feat", "PUSH_SHA": head, "GITHUB_OUTPUT": str(out)}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(repo)
    assert plan.default_branch_sha(str(repo)) is None
    assert plan.main() == 0
    assert "macos=true" in out.read_text()


# --- workflow shape for the macOS tiering ---------------------------------------------

def _macos_steps():
    return {s["name"]: s for s in _wf()["jobs"]["macos"]["steps"]}


def test_stock_python_steps_and_apple_gate_tests_run_on_the_py39_leg_only():
    steps = _macos_steps()
    for name in ("Stock /usr/bin/python3 really lacks PyYAML",
                 "Gate tests under Apple's /usr/bin/python3",
                 "create-tess tests, wizard on stock /usr/bin/python3",
                 "Fresh-install e2e from the packed tarball, stock /usr/bin/python3"):
        assert steps[name].get("if") == "matrix.python-version == '3.9'", name


def test_the_apple_python_step_uses_a_throwaway_venv_a_timeout_and_the_gate_files():
    import re
    step = _macos_steps()["Gate tests under Apple's /usr/bin/python3"]
    assert isinstance(step["timeout-minutes"], int) and 0 < step["timeout-minutes"] <= 30
    run = step["run"]
    assert "/usr/bin/python3 -m venv" in run and "RUNNER_TEMP" in run
    assert "pip install" in run and "requirements-dev.txt" in run
    # the version is asserted, not only printed (a changed runner image must fail the step)
    assert "sys.version_info[:2] == (3, 9)" in run and "exit 1" in run
    assert "-rfEs" in run
    files = re.findall(r"tests/(test_\w+\.py)", run)
    # one list: the step runs exactly APPLE_GATE_TESTS, and every file it runs (and every
    # fixture module those import) is a gate path that forces the macOS legs
    assert sorted(files) == sorted(plan.APPLE_GATE_TESTS) and len(set(files)) == len(files)
    for f in files + list(plan.APPLE_GATE_SUPPORT):
        assert (REPO / "tests" / f).exists(), f
        assert plan.touches_gate(["tests/" + f]) is True, f


def test_every_gate_runtime_input_in_the_patterns_exists_in_the_repo():
    # (.gemini/settings.json is not in this repository, so it is deliberately not a pattern.)
    for rel in ("scripts/brain", "core/contracts", "tess.manifest.json", ".claude/hooks", "core/policy"):
        assert (REPO / rel).exists(), rel


def test_the_macos_pytest_step_runs_under_xdist_with_three_workers():
    step = _macos_steps()["Run test suite (pytest, -n 3)"]
    assert "-n 3" in step["run"] and "test_v1_first_push_release_proof" in step["run"]
    assert "-rfEs" in step["run"]    # keep the FAILED/ERROR short summary (-rs alone replaces addopts -ra)
    assert "pytest-xdist" in (REPO / "requirements-dev.txt").read_text()


def test_the_plan_job_passes_the_push_sha_and_exports_the_matrix():
    plan_job = _wf()["jobs"]["plan"]
    assert "macos_pythons" in plan_job["outputs"]
    env = next(s for s in plan_job["steps"] if s.get("id") == "plan")["env"]
    assert env["PUSH_SHA"] == "${{ github.sha }}"


# --- PR lookup: every error path fails closed ----------------------------------------

class _Resp:
    def __init__(self, payload):
        import io
        self._b = io.BytesIO(payload if isinstance(payload, bytes) else __import__("json").dumps(payload).encode())

    def read(self, *a):
        return self._b.read(*a)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _pr_obj(base="main", repo="o/r", sha="a" * 40):
    return {"base": {"ref": base}, "head": {"repo": {"full_name": repo}, "sha": sha}}


def _lookup(monkeypatch, payload=None, exc=None, token="t", repo="o/r", branch="rc/v1", sha=""):
    def fake(req, timeout=None):
        assert timeout and timeout > 0              # never an unbounded wait
        if exc is not None:
            raise exc
        return _Resp(payload)
    monkeypatch.setattr(plan.urllib.request, "urlopen", fake)
    return plan.open_pr_to_default_branch(repo, branch, token, sha)


@pytest.mark.parametrize("exc", [
    TimeoutError("timed out"), OSError("network down"), __import__("urllib.error").error.URLError("dns"),
    __import__("urllib.error").error.HTTPError("u", 403, "rate limited", {}, __import__("io").BytesIO(b"")), RuntimeError("boom"),
])
def test_pr_lookup_errors_return_none(monkeypatch, exc):
    assert _lookup(monkeypatch, exc=exc) is None


@pytest.mark.parametrize("payload", [b"not json", b"", b"{", {"message": "Bad credentials"}, "text", 7, None])
def test_pr_lookup_bad_payload_returns_none(monkeypatch, payload):
    assert _lookup(monkeypatch, payload=payload) is None


@pytest.mark.parametrize("pr", [{}, {"base": {"ref": "main"}}, {"base": {"ref": "main"}, "head": None},
                                {"base": None, "head": {}}, {"base": {"ref": "main"}, "head": {"repo": None}}, "x", 3])
def test_pr_lookup_malformed_pr_objects_return_none(monkeypatch, pr):
    assert _lookup(monkeypatch, payload=[pr]) is None


@pytest.mark.parametrize("kw", [{"token": ""}, {"repo": ""}, {"branch": ""}])
def test_pr_lookup_missing_inputs_return_none_without_a_request(monkeypatch, kw):
    def boom(*a, **k):
        raise AssertionError("no request may be made")
    monkeypatch.setattr(plan.urllib.request, "urlopen", boom)
    args = dict(repo="o/r", branch="rc/v1", token="t")
    args.update(kw)
    assert plan.open_pr_to_default_branch(**args) is None


def test_pr_lookup_answers(monkeypatch):
    assert _lookup(monkeypatch, payload=[]) is False
    assert _lookup(monkeypatch, payload=[_pr_obj()]) is True
    assert _lookup(monkeypatch, payload=[_pr_obj(base="rc/v1")]) is False          # PR into another branch
    assert _lookup(monkeypatch, payload=[_pr_obj(repo="fork/r")]) is False         # fork head
    # the PR run owns the push only if its head IS the pushed commit
    assert _lookup(monkeypatch, payload=[_pr_obj(sha="a" * 40)], sha="a" * 40) is True
    assert _lookup(monkeypatch, payload=[_pr_obj(sha="a" * 40)], sha="b" * 40) is False
    assert _lookup(monkeypatch, payload=[{"base": {"ref": "main"}, "head": {"repo": {"full_name": "o/r"}}}], sha="b" * 40) is None


@pytest.mark.parametrize("exc", [TimeoutError("t"), OSError("o"), ValueError("v")])
def test_a_failed_pr_lookup_runs_macos_end_to_end(monkeypatch, tmp_path, exc):
    out = tmp_path / "out"
    out.write_text("")
    for k, v in {"EVENT_NAME": "push", "REF_NAME": "rc/v1.0.0", "REPO": "o/r", "GITHUB_TOKEN": "t",
                 "PUSH_SHA": "c" * 40, "GITHUB_OUTPUT": str(out)}.items():
        monkeypatch.setenv(k, v)

    def fake(req, timeout=None):
        raise exc
    monkeypatch.setattr(plan.urllib.request, "urlopen", fake)
    assert plan.main() == 0
    assert "macos=true" in out.read_text()


def test_a_pr_owned_integration_push_with_a_gate_change_runs_macos_end_to_end(repo, monkeypatch, tmp_path):
    base = _commit(repo, "a.txt")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    _git(repo, "checkout", "-q", "-b", "rc/v1.0.0")
    head = _commit(repo, ".claude/hooks/tess-gate.py")
    out = tmp_path / "out"
    out.write_text("")
    for k, v in {"EVENT_NAME": "push", "REF_NAME": "rc/v1.0.0", "REPO": "o/r", "GITHUB_TOKEN": "t",
                 "PUSH_SHA": head, "GITHUB_OUTPUT": str(out)}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(plan.urllib.request, "urlopen", lambda req, timeout=None: _Resp([_pr_obj(sha=head)]))
    monkeypatch.chdir(repo)
    assert plan.main() == 0
    assert "macos=true" in out.read_text()
    # and the negative: a docs-only integration push owned by that PR skips
    _git(repo, "checkout", "-q", "-b", "rc/v1.0.1", base)
    head3 = _commit(repo, "docs/note.md")
    monkeypatch.setenv("REF_NAME", "rc/v1.0.1")
    monkeypatch.setenv("PUSH_SHA", head3)
    monkeypatch.setattr(plan.urllib.request, "urlopen", lambda req, timeout=None: _Resp([_pr_obj(sha=head3)]))
    out.write_text("")
    assert plan.main() == 0
    assert "macos=false" in out.read_text()


def test_main_exits_nonzero_when_github_output_is_unset_in_ci(monkeypatch):
    for k in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY", "REF_NAME"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("EVENT_NAME", "push")
    monkeypatch.setenv("REF_NAME", "main")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert plan.main() == 1
    monkeypatch.delenv("GITHUB_ACTIONS")
    assert plan.main() == 0         # local run: print only


# --- feature pushes diff against the integration branch they were cut from -------------

def _clone_with_lines(tmp_path):
    """A repo whose origin/main is old and whose origin/rc/v1 is far ahead of it with gate files."""
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    main = _commit(r, "a.txt")
    _git(r, "update-ref", "refs/remotes/origin/main", main)
    _git(r, "checkout", "-q", "-b", "rc/v1")
    _commit(r, ".claude/hooks/tess-gate.py")
    _commit(r, "scripts/brain/x.py")
    rc = _commit(r, "app/y.py")
    _git(r, "update-ref", "refs/remotes/origin/rc/v1", rc)
    return r, main, rc


def _plan_push(repo, head, monkeypatch, tmp_path, ref="feat"):
    out = tmp_path / "out"
    out.write_text("")
    for k, v in {"EVENT_NAME": "push", "REF_NAME": ref, "PUSH_SHA": head, "GITHUB_OUTPUT": str(out)}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(repo)
    assert plan.main() == 0
    return dict(l.split("=", 1) for l in out.read_text().splitlines())


def test_ordinary_branch_cut_from_rc_skips_macos(tmp_path, monkeypatch):
    r, main, rc = _clone_with_lines(tmp_path)
    _git(r, "checkout", "-q", "-b", "feat")
    head = _commit(r, "app/new.py")
    assert plan.touches_gate(plan.changed_files(main, head, str(r))) is True  # the old base: false alarm
    assert plan.feature_base_changed_files(head, str(r)) == ["app/new.py"]
    assert _plan_push(r, head, monkeypatch, tmp_path)["macos"] == "false"


def test_gate_edit_on_a_branch_cut_from_rc_runs_macos(tmp_path, monkeypatch):
    r, main, rc = _clone_with_lines(tmp_path)
    _git(r, "checkout", "-q", "-b", "feat")
    _commit(r, ".github/scripts/ci_plan.py")
    head = _commit(r, "docs/n.md")
    assert plan.feature_base_changed_files(head, str(r)) == [".github/scripts/ci_plan.py", "docs/n.md"]
    assert _plan_push(r, head, monkeypatch, tmp_path)["macos"] == "true"


def test_branch_cut_from_main_behaves_as_before(tmp_path, monkeypatch):
    r, main, rc = _clone_with_lines(tmp_path)
    _git(r, "checkout", "-q", "-b", "feat", main)
    head = _commit(r, "app/new.py")
    assert plan.feature_base_changed_files(head, str(r)) == ["app/new.py"]
    assert _plan_push(r, head, monkeypatch, tmp_path)["macos"] == "false"
    _git(r, "checkout", "-q", "-b", "feat2", main)
    head2 = _commit(r, "tessctl")
    assert _plan_push(r, head2, monkeypatch, tmp_path)["macos"] == "true"


def test_the_candidate_with_the_fewest_changes_wins_not_the_most(tmp_path):
    r, main, rc = _clone_with_lines(tmp_path)
    _git(r, "checkout", "-q", "-b", "feat")
    head = _commit(r, "app/new.py")
    got = plan.feature_base_changed_files(head, str(r))
    assert got == ["app/new.py"] and len(plan.changed_files(main, head, str(r))) == 4


def test_release_branches_are_candidates_too(tmp_path):
    r, main, rc = _clone_with_lines(tmp_path)
    _git(r, "checkout", "-q", "-b", "release/v1")
    rel = _commit(r, "scripts/brain/z.py")
    _git(r, "update-ref", "refs/remotes/origin/release/v1", rel)
    head = _commit(r, "app/q.py")
    assert plan.feature_base_changed_files(head, str(r)) == ["app/q.py"]


def test_a_tie_between_candidates_keeps_both_diffs_fail_closed(tmp_path, monkeypatch):
    r = tmp_path / "u"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    base = _commit(r, "a.txt")
    _git(r, "update-ref", "refs/remotes/origin/main", base)
    _git(r, "checkout", "-q", "-b", "rc/a")
    _git(r, "update-ref", "refs/remotes/origin/rc/a", _commit(r, ".claude/hooks/a.py"))  # gate file
    _git(r, "checkout", "-q", "-b", "rc/b", base)
    _git(r, "update-ref", "refs/remotes/origin/rc/b", _commit(r, "rb.py"))
    # feature = both rc tips + f.py. Against rc/a: {rb.py, f.py}; rc/b: {.claude/hooks/a.py, f.py};
    # main: 3 files. The two rc candidates tie at 2 files; picking only rc/a would hide the gate file.
    _git(r, "checkout", "-q", "-b", "feat", "rc/a")
    _git(r, "merge", "-q", "--no-edit", "rc/b")
    head = _commit(r, "f.py")
    assert plan.feature_base_changed_files(head, str(r)) == [".claude/hooks/a.py", "f.py", "rb.py"]
    assert _plan_push(r, head, monkeypatch, tmp_path)["macos"] == "true"


def test_no_default_branch_ref_means_no_plan(tmp_path):
    r = tmp_path / "n"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    head = _commit(r, "a.txt")
    assert plan.feature_base_changed_files(head, str(r)) is None


def test_missing_default_branch_ref_fails_closed_even_when_rc_resolves(tmp_path):
    r, main, rc = _clone_with_lines(tmp_path)
    _git(r, "checkout", "-q", "-b", "feat")
    head = _commit(r, "app/new.py")
    _git(r, "update-ref", "-d", "refs/remotes/origin/main")
    assert plan.feature_base_changed_files(head, str(r)) is None


def test_a_shallow_clone_fails_closed(tmp_path, monkeypatch):
    r, main, rc = _clone_with_lines(tmp_path)
    _git(r, "checkout", "-q", "-b", "feat")
    head = _commit(r, "app/new.py")
    assert plan.feature_base_changed_files(head, str(r)) == ["app/new.py"]  # complete clone: computable
    (r / ".git" / "shallow").write_text(main + "\n")  # history cut at main; the diff is still computable
    assert plan.changed_files(rc, head, str(r)) == ["app/new.py"]
    assert plan.feature_base_changed_files(head, str(r)) is None
    assert _plan_push(r, head, monkeypatch, tmp_path)["macos"] == "true"


def test_a_candidate_whose_merge_base_fails_fails_closed(tmp_path, monkeypatch):
    r, main, rc = _clone_with_lines(tmp_path)
    # unrelated history under origin/rc/orphan: merge-base fails
    _git(r, "checkout", "-q", "--orphan", "orph")
    _git(r, "rm", "-rqf", ".")
    orphan = _commit(r, "o.txt")
    _git(r, "update-ref", "refs/remotes/origin/rc/orphan", orphan)
    _git(r, "checkout", "-q", "-b", "feat", rc)
    head = _commit(r, "app/new.py")
    assert plan.feature_base_changed_files(head, str(r)) is None
    assert _plan_push(r, head, monkeypatch, tmp_path)["macos"] == "true"


def test_an_unusable_head_sha_fails_closed(tmp_path):
    r, main, rc = _clone_with_lines(tmp_path)
    assert plan.feature_base_changed_files("nothex", str(r)) is None


def test_the_plan_job_checkout_has_full_history_and_all_branch_refs():
    step = _wf()["jobs"]["plan"]["steps"][0]
    assert step["with"]["fetch-depth"] == 0  # every branch (main, rc/*, release/*) and full history
    assert not step["with"].get("ref") and not step["with"].get("fetch-tags")


def test_pr_owned_integration_pushes_still_diff_against_main(tmp_path, monkeypatch):
    r, main, rc = _clone_with_lines(tmp_path)
    monkeypatch.setattr(plan, "open_pr_to_default_branch", lambda *a, **k: True)
    assert _plan_push(r, rc, monkeypatch, tmp_path, ref="rc/v1")["macos"] == "true"


# --- repeatable dev-dependency installs -------------------------------------------

WORKFLOWS_WITH_DEV_INSTALLS = {"ci.yml": 5, "release.yml": 1}   # exact install counts
CONSTRAINTS = ".github/ci-constraints.txt"


def _steps(wf_name):
    wf = yaml.safe_load((REPO / ".github" / "workflows" / wf_name).read_text(encoding="utf-8"))
    return [s for job in wf["jobs"].values() for s in job.get("steps", [])]


def test_every_workflow_dev_install_uses_the_ci_constraints_file():
    import re
    for wf_name, expected in WORKFLOWS_WITH_DEV_INSTALLS.items():
        installs = []
        cache_steps = 0
        for step in _steps(wf_name):
            # join shell line continuations so a wrapped command is one command
            run = (step.get("run") or "").replace("\\\n", " ")
            installs += re.findall(r"pip3? install\b[^\n]*requirements-dev\.txt[^\n]*", run)
            cache = (step.get("with") or {}).get("cache-dependency-path")
            if cache and "requirements-dev.txt" in cache:
                cache_steps += 1
                # setup-python's pip cache is keyed on both files, so a pin bump busts it
                assert sorted(cache.split()) == sorted(["requirements-dev.txt", CONSTRAINTS]), (wf_name, cache)
        assert len(installs) == expected, (wf_name, installs)
        for cmd in installs:
            assert f"-c {CONSTRAINTS}" in cmd, (wf_name, cmd)
        assert cache_steps >= 1, wf_name


# Every package pip installs from requirements-dev.txt, per Python that CI runs, with
# dependencies of dependencies. When a pin is bumped or a dependency appears, update
# this table and ci-constraints.txt together; the test fails if they disagree.
EXPECTED_PINNED = {
    "3.9": {"pytest", "pytest-xdist", "pyyaml", "pyrage", "execnet", "iniconfig", "packaging",
            "pluggy", "pygments", "exceptiongroup", "tomli", "typing-extensions"},
    "3.12": {"pytest", "pytest-xdist", "pyyaml", "pyrage", "execnet", "iniconfig", "packaging",
             "pluggy", "pygments"},
}


def test_the_ci_constraints_pin_every_dev_requirement_exactly_for_each_python():
    import re
    from packaging.markers import Marker
    entries = []
    for line in (REPO / CONSTRAINTS).read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"([A-Za-z0-9_.-]+)==([0-9][^;\s]*)\s*(?:;\s*(.*))?", line)
        assert m, f"not an exact pin: {line!r}"
        entries.append((re.sub(r"[-_.]+", "-", m[1]).lower(), m[2], m[3]))
    direct = set()
    for line in (REPO / "requirements-dev.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            direct.add(re.sub(r"[-_.]+", "-", re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0]).lower())
    for py, expected in EXPECTED_PINNED.items():
        env = {"python_version": py, "python_full_version": py + ".0"}
        names = [n for n, _v, marker in entries if marker is None or Marker(marker).evaluate(env)]
        assert len(names) == len(set(names)), f"python {py}: a package is pinned twice: {sorted(names)}"
        assert set(names) == expected, (
            f"python {py}: missing pins {sorted(expected - set(names))}, unexpected pins {sorted(set(names) - expected)}")
        assert direct <= set(names), (py, sorted(direct - set(names)))
