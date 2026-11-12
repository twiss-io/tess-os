#!/usr/bin/env python3
"""ci_plan.py -- decide whether CI's macOS legs run for this event.

Only the macOS jobs (the stock-macOS suite and the macOS shell-conformance
leg) are planned here. They are the most expensive part of CI and none of
them is a required status check. Every Linux job -- including every required
check -- runs on every event; this script cannot skip them.

Two decisions:
  macos         the macOS py3.9 leg (pytest, stock-Python steps, Apple-Python gate
                tests) and the macOS shell conformance leg run.
  macos_full    the macOS py3.12 pytest leg runs too. Only on a pull request to the
                default branch, a push to it, or a manual dispatch with macos=true:
                it caught nothing the py3.9 leg and Linux did not.

A change to the gate, the engine, the shell-conformance code or the pins
(GATE_PATTERNS) forces `macos` on every event, including feature pushes and
pull requests into rc/release branches.

Fail closed: any input that is missing, unknown or uncomputable means the
macOS legs RUN.

Reads its inputs from the environment (never from argv or interpolated
workflow text) and writes `macos`, `macos_full`, `macos_pythons`,
`conformance_os` and `reason` to $GITHUB_OUTPUT. Stdlib only.

SPDX-License-Identifier: Apache-2.0
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.request
from typing import Optional, Sequence, Tuple

DEFAULT_BRANCH = "main"
# Branches whose every push gets the full (macOS) run.
INTEGRATION_GLOBS = ("release/*", "rc/*")

# Paths that cannot change what a macOS leg tests: prose and static assets under
# docs/, the root community files, and the issue/PR templates. Everything else
# (code, tests, workflows, scripts, pins, lockfiles, templates, hooks, policy,
# unknown paths) is NOT listed, so it triggers the macOS run.
_DOC_PATTERNS = (
    re.compile(r"docs/.+\.(md|txt|png|jpe?g|gif|svg|webp)"),
    re.compile(r"(README|CHANGELOG|CONTRIBUTING|CODE_OF_CONDUCT|SECURITY|TRADEMARK|CLA)\.md"),
    re.compile(r"(LICENSE|NOTICE)"),
    re.compile(r"\.github/ISSUE_TEMPLATE/.+\.(md|yml)"),
    re.compile(r"\.github/PULL_REQUEST_TEMPLATE\.md"),
)

# The test files the macOS py3.9 leg runs under Apple's python3 (the "Gate tests under
# Apple's /usr/bin/python3" step in ci.yml). tests/test_ci_plan.py asserts that the step's
# file list equals this tuple, so the step and GATE_PATTERNS cannot drift apart.
APPLE_GATE_TESTS = (
    "test_v1_b1_class.py", "test_v1_round4_shell_model.py", "test_v1_r6_gate_expand.py",
    "test_hook_pinning.py", "test_e8_fail_closed.py", "test_v1_r2_isolation.py",
)
# Fixture modules those tests import (they load the gate and define the ALLOW/ASK/DENY
# decisions); the step does not collect them, but editing one changes what the step proves.
APPLE_GATE_SUPPORT = ("test_v1_n1_n3.py",)

# Paths whose change can alter what the gate, the engine or the shell model does on
# a stock Mac (Apple python3 3.9.6, bash 3.2): the only real Linux-invisible bug so
# far was a gate bypass of that kind. A diff touching any of them runs the macOS
# py3.9 and conformance legs on every event. Docs-only paths never match.
# Matched case-INsensitively: macOS file systems are, so `.CLAUDE/hooks/x` collides
# with the real hook there. Keep tests/test_ci_plan.py::GATE_PATH_EXAMPLES in step.
_GATE_REGEXES = (
    r"\.claude/hooks/.+",                      # tess-gate.py, run-pinned.py, ...
    r"\.claude/settings[^/]*\.json",          # registers the hooks
    r"\.codex/(hooks|config)[^/]*(/.+)?",
    r"\.tess/(bin|core|vendor|keys)/.+",       # tessctl, pinned scripts, vendored YAML
    r"\.tess/tess\.lock",
    r"tessctl",
    r"core/policy/.+",
    r"core/contracts/.+",                      # schemas the gate and engine validate against
    r"scripts/brain/.+",                       # pinned hook closure, run via run-pinned.py
    r"tess\.manifest\.json",
    r"(requirements-dev\.txt|\.github/ci-constraints\.txt|uv\.lock|pyproject\.toml|\.python-version|pytest\.ini)",
    r"create-tess/package(-lock)?\.json",
    r"tests/(shell_conformance|gate_corpus_recorder|conftest)\.py",
    r"tests/test_v1_shell_conformance\.py",
    r"\.github/(workflows/ci\.yml|scripts/ci_plan\.py)",
    r"tests/test_ci_plan\.py",
) + tuple(re.escape("tests/" + n) for n in APPLE_GATE_TESTS + APPLE_GATE_SUPPORT)
GATE_PATTERNS = tuple(re.compile(r, re.IGNORECASE) for r in _GATE_REGEXES)

ALL_OS = ["ubuntu-latest", "macos-latest"]
LINUX_ONLY = ["ubuntu-latest"]


def is_integration_branch(name: str) -> bool:
    return name == DEFAULT_BRANCH or any(fnmatch.fnmatchcase(name, g) for g in INTEGRATION_GLOBS)


def is_docs_path(path: str) -> bool:
    if ".." in path.split("/") or path.startswith("/"):
        return False
    return any(p.fullmatch(path) for p in _DOC_PATTERNS)


def touches_gate(changed: Optional[Sequence[str]]) -> bool:
    """True if any changed path is a gate / engine / shell-conformance / pin path."""
    return bool(changed) and any(
        ".." in p.split("/") or p.startswith("/") or any(g.fullmatch(p) for g in GATE_PATTERNS)  # odd path: fail closed
        for p in changed)


def docs_only(changed: Optional[Sequence[str]]) -> bool:
    """True only for a computed, non-empty change list made entirely of docs paths."""
    return bool(changed) and all(is_docs_path(p) for p in changed)


def decide(
    event: str,
    ref_name: str,
    base_ref: str,
    same_repo: bool,
    changed: Optional[Sequence[str]],
    open_pr_to_default: Optional[bool],
    dispatch_macos: str,
) -> Tuple[bool, str]:
    """Return (run_macos, reason): the macOS py3.9 leg and the macOS conformance leg."""
    if event == "workflow_dispatch":
        if dispatch_macos.strip().lower() == "false":
            return False, "manual dispatch with macos=false"
        return True, "manual dispatch"
    if event == "push":
        if ref_name == DEFAULT_BRANCH:
            return True, "push to the default branch"
        if is_integration_branch(ref_name):
            if open_pr_to_default is False or open_pr_to_default is None:
                why = "no open PR to the default branch" if open_pr_to_default is False else "PR lookup failed, failing closed"
                return True, "push to integration branch (%s)" % why
            # A PR's pull_request run may never start (merge conflict) or be superseded, so a
            # gate change is never left to it: the gate rule applies to PR-owned pushes too.
            return _unless_gate(changed, "integration branch with an open PR to the default branch: the pull_request run owns the macOS legs for this head")
        return _unless_gate(changed, "push to a non-integration branch: macOS runs at the pull request / on the integration branch (dispatch to force)")
    if event == "pull_request":
        if not same_repo:
            return True, "pull request from a fork or unknown head repository"
        if changed is None:
            return True, "PR diff could not be computed, failing closed"
        if not changed:
            return True, "PR diff is empty, failing closed"
        if base_ref != DEFAULT_BRANCH and is_integration_branch(base_ref):
            return _unless_gate(changed, "pull request into integration branch %s: the merge push there runs macOS" % base_ref)
        if docs_only(changed):
            return False, "cumulative PR diff is docs-only (%d files)" % len(changed)
        return True, "cumulative PR diff touches non-docs paths"
    return True, "unrecognised event %r, failing closed" % event


def _unless_gate(changed: Optional[Sequence[str]], skip_reason: str) -> Tuple[bool, str]:
    """A would-be skip still runs when the cumulative diff touches the gate, the engine or the
    shell-conformance code, and when the diff cannot be computed (fail closed)."""
    if changed is None:
        return True, "diff against the default branch could not be computed, failing closed"
    if touches_gate(changed):
        return True, "cumulative diff touches the gate, the engine, the shell-conformance code or the pins"
    return False, skip_reason


def decide_full(event: str, ref_name: str, base_ref: str, run_macos: bool, dispatch_macos: str) -> bool:
    """Does the macOS py3.12 pytest leg run too? Only where it is the last look before (or
    right after) the default branch moves: a PR to it, a push to it, a manual full run."""
    if not run_macos:
        return False
    if event == "workflow_dispatch":
        return dispatch_macos.strip().lower() != "false"
    if event == "push":
        return ref_name == DEFAULT_BRANCH
    if event == "pull_request":
        return base_ref == DEFAULT_BRANCH
    return True  # unrecognised event: fail closed


def changed_files(base_sha: str, head_sha: str, cwd: Optional[str] = None) -> Optional[list]:
    """Cumulative diff of head against its merge base with base. None if uncomputable."""
    if not re.fullmatch(r"[0-9a-f]{40,64}", base_sha or "") or not re.fullmatch(r"[0-9a-f]{40,64}", head_sha or ""):
        return None

    def run(*args: str) -> Optional[str]:
        r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
        return r.stdout if r.returncode == 0 else None

    mb = run("merge-base", base_sha, head_sha)
    if not mb or not mb.strip():
        return None
    out = run("diff", "--name-only", "--no-renames", "-z", mb.strip(), head_sha)
    if out is None:
        return None
    return [p for p in out.split("\0") if p]


def _git_out(*args: str, cwd: Optional[str] = None) -> Optional[str]:
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    return r.stdout if r.returncode == 0 else None


def feature_base_changed_files(head_sha: str, cwd: Optional[str] = None) -> Optional[list]:
    """Changed files of a feature push against the integration branch it was cut from.

    Candidates: origin/main, origin/rc/*, origin/release/*. For each, the files changed between
    its merge base with HEAD and HEAD; the candidate with the FEWEST wins (the branch this one
    forked from). The base branch's own push run already gave a gate change there its macOS
    run, so only what this branch adds on top needs deciding. On a tie the UNION of the tied
    diffs is returned (fail closed). None -- macOS runs -- if the clone is shallow, the default
    branch ref is missing, or any git step on a candidate fails.
    """
    if (_git_out("rev-parse", "--is-shallow-repository", cwd=cwd) or "").strip() != "false":
        return None
    main_sha = default_branch_sha(cwd)
    if not main_sha:
        return None
    refs = _git_out("for-each-ref", "--format=%(objectname)", "refs/remotes/origin/rc/",
                    "refs/remotes/origin/release/", cwd=cwd)
    if refs is None:
        return None
    shas = [main_sha] + sorted({r.strip() for r in refs.splitlines() if r.strip()} - {main_sha})
    results = []
    for sha in shas:
        files = changed_files(sha, head_sha, cwd)
        if files is None:
            return None  # a candidate that cannot be diffed: do not guess
        results.append(set(files))
    fewest = min(len(r) for r in results)
    out = set().union(*(r for r in results if len(r) == fewest))
    return sorted(out)


def default_branch_sha(cwd: Optional[str] = None) -> Optional[str]:
    """The checked-out remote default branch tip, or None."""
    r = subprocess.run(["git", "rev-parse", "--verify", "-q", "refs/remotes/origin/%s^{commit}" % DEFAULT_BRANCH],
                       capture_output=True, text=True, cwd=cwd)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def open_pr_to_default_branch(repo: str, branch: str, token: str, push_sha: str = "") -> Optional[bool]:
    """Is there an open same-repo PR from `branch` into the default branch whose head is this
    push (when `push_sha` is given)? None on any error: the caller fails closed."""
    if not (repo and branch and token):
        return None
    owner = repo.split("/")[0]
    url = "https://api.github.com/repos/%s/pulls?state=open&per_page=100&head=%s" % (
        repo, urllib.request.quote("%s:%s" % (owner, branch), safe=""))
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            prs = json.load(resp)
    except Exception as exc:  # network, auth, JSON: all fail closed
        print("ci_plan: PR lookup failed (%s)" % type(exc).__name__, file=sys.stderr)
        return None
    if not isinstance(prs, list):
        return None
    for pr in prs:
        try:
            if pr["base"]["ref"] == DEFAULT_BRANCH and pr["head"]["repo"]["full_name"] == repo:
                if push_sha and pr["head"]["sha"] != push_sha:
                    continue  # the PR run is for another head: it does not own this push
                return True
        except (KeyError, TypeError):
            return None
    return False


def main() -> int:
    env = os.environ
    event = env.get("EVENT_NAME", "")
    repo = env.get("REPO", "")
    head_repo = env.get("HEAD_REPO", "")
    changed = None
    open_pr: Optional[bool] = None
    if event == "pull_request":
        changed = changed_files(env.get("BASE_SHA", ""), env.get("HEAD_SHA", ""))
    elif event == "push" and is_integration_branch(env.get("REF_NAME", "")) and env.get("REF_NAME") != DEFAULT_BRANCH:
        open_pr = open_pr_to_default_branch(repo, env.get("REF_NAME", ""), env.get("GITHUB_TOKEN", ""), env.get("PUSH_SHA", ""))
        # Cumulative diff against the default branch (deliberately NOT the nearest base: the
        # release line itself must get macOS while it is ahead of main). The gate rule applies
        # even when a PR owns the head.
        changed = changed_files(default_branch_sha() or "", env.get("PUSH_SHA", ""))
    elif event == "push" and env.get("REF_NAME") != DEFAULT_BRANCH:
        # Feature push: the cumulative diff against the nearest integration base (the branch it
        # was cut from: main, rc/* or release/*), not just this push and not always main.
        changed = feature_base_changed_files(env.get("PUSH_SHA", ""))
    macos, reason = decide(
        event, env.get("REF_NAME", ""), env.get("BASE_REF", ""),
        bool(repo) and head_repo == repo, changed, open_pr, env.get("DISPATCH_MACOS", "true"))
    full = decide_full(event, env.get("REF_NAME", ""), env.get("BASE_REF", ""), macos, env.get("DISPATCH_MACOS", "true"))
    line = "macOS legs: %s (py3.12 pytest: %s) -- %s" % ("RUN" if macos else "SKIP", "RUN" if full else "SKIP", reason)
    print(line)
    out = env.get("GITHUB_OUTPUT")
    if not out and env.get("GITHUB_ACTIONS"):
        print("ci_plan: GITHUB_OUTPUT is not set in CI; the workflow would get no plan", file=sys.stderr)
        return 1
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("macos=%s\n" % ("true" if macos else "false"))
            fh.write("macos_full=%s\n" % ("true" if full else "false"))
            fh.write("macos_pythons=%s\n" % json.dumps(["3.9", "3.12"] if full else ["3.9"]))
            fh.write("conformance_os=%s\n" % json.dumps(ALL_OS if macos else LINUX_ONLY))
            fh.write("reason=%s\n" % reason.replace("\n", " "))
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("### CI plan\n\n%s\n\nLinux jobs (all required checks) always run.\n" % line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
