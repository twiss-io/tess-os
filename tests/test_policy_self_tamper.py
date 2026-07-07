"""
A3 — policy self-tamper (Gate Arena finding, disclosed 2026-07-07, PR #50 on
`goal-gate-arena`, `gate-arena/results/bypass-scorecard.md`):

    "Deleting or weakening policy.yaml's own self-gating rule in the SAME
    push as an unreviewed payload is NOT caught: `_gate_load_policy` reads
    the policy off the checked-out working tree with no base-ref pin and no
    diff-against-previous-policy check. So an attacker weakens the rule
    that would have gated their bad code, in the same PR, and ships both."

Fix: `tessctl gate` now classifies changed paths against the UNION of what
the NEW (just-pushed) policy requires and what the BASELINE (pre-push,
base-ref) policy ALREADY required (`_gate_load_policy_at_base` +
`_gate_union_baseline_matches` in `.tess/bin/tessctl`). A rule's
requirement, once true at the base ref, cannot be made to silently stop
applying to THIS push's own changes.

Coverage:
  1. THE disclosed attack, reproduced almost verbatim from the Gate Arena's
     own `attack_A3_policy_tamper_same_push`: both the self-gating rule
     (covering `core/policy/**`) and the ordinary `prod-src` rule are
     DELETED entirely, in the same commit as an unreviewed `src/prod/
     app.py` change — must BLOCK.
  2. The softer variant: rules kept, but their `globs` are NARROWED past
     matching the very paths changed in this push — must still BLOCK.
  3. The `allowed_verifiers`-widening chained variant: a rule is kept
     (globs/require_verdict unchanged), but `allowed_verifiers` gains a
     brand-new name in the SAME push that also registers a real key for
     that name and self-signs with it — the effective allowed_verifiers
     for this push is the intersection with baseline, so the newly-added
     name does not count.
  4. The `verifier_keys` fingerprint-swap chained variant: an
     already-allowed verifier's REGISTERED KEY is swapped for one the
     attacker controls, in the same push, self-signing as that verifier —
     signature verification prefers the baseline's registered fingerprint,
     so the forged signature does not match.
  5. Regression / sanity: a genuine, non-tampering policy edit (a brand
     new, unrelated rule added) with a REAL covering verdict from an
     allowed verifier still PASSES — the fix must not break legitimate
     policy evolution.
  6. Regression / sanity: an ordinary prod change with a genuine covering
     verdict, policy entirely untouched, still PASSES — no false positive
     from the new baseline-union machinery when nothing in policy changed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import sign_verdict_for_test

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"

HAS_GIT = shutil.which("git") is not None
HAS_GPG = shutil.which("gpg") is not None
pytestmark = pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")


def _git(root, *args, check=True, input_text=None):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@tess.test",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@tess.test",
    }
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, env=env, input=input_text,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
    return r


def _init_repo(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@tess.test")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "commit.gpgsign", "false")


def _base_sha(root):
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _commit_all(root, message):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _blob_sha(root, rel_path):
    return _git(root, "hash-object", rel_path).stdout.strip()


def _bundle_key(root, name, key):
    keys_dir = root / ".tess" / "keys" / "verifiers"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / f"{name.lower()}.asc").write_text(key.pubkey_armored, encoding="utf-8")
    return f".tess/keys/verifiers/{name.lower()}.asc"


def _tamper_verdict(covers_paths, artifact_hashes, verifier="Reid"):
    return {
        "verifier": verifier,
        "output_domain": "Code diff / PR",
        "primary_artifacts_read": list(covers_paths),
        "findings": [],
        "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "summary_line": "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none.",
        "disposition": "APPROVE",
        "covers_paths": list(covers_paths),
        "artifact_hashes": dict(artifact_hashes),
    }


def _write_verdict(root, rel_path, verdict_dict):
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\n" + yaml.safe_dump(verdict_dict) + "---\n\n# Verdict body\n", encoding="utf-8")
    return p


def _self_tamper_policy_dict(verifier_keys):
    """A policy with a self-gating rule protecting `core/policy/**` (the
    same shape as this repo's own shipped `tess-os-security-tier-doctrine`
    rule) PLUS one ordinary `prod-src` rule — mirrors the Gate Arena's own
    `lib._forked_policy_dict` fixture design (fork the real self-gating
    shape, add one ordinary non-self-referential rule)."""
    return {
        "policy": {
            "version": 1,
            "rules": [
                {
                    "id": "self-gate",
                    "description": "Protects core/policy/** — this fixture's stand-in for the real tess-os-security-tier-doctrine rule.",
                    "globs": ["core/policy/**"],
                    "classification": ["prod_touching"],
                    "require_verdict": True,
                    "allowed_verifiers": ["Reid", "Cyra"],
                },
                {
                    "id": "prod-src",
                    "description": "Ordinary application code, non-self-referential.",
                    "globs": ["src/prod/**"],
                    "classification": ["prod_touching"],
                    "require_verdict": True,
                    "allowed_verifiers": ["Reid"],
                },
            ],
            "hard_floor_rules": [],
            "verifier_keys": verifier_keys,
        }
    }


@pytest.fixture
def tamper_repo(project, verifier_gpg_keys):
    """A real git repo: real contract schemas, a self-gating policy (see
    `_self_tamper_policy_dict`) with Reid's + Cyra's real keys registered,
    and ONE baseline commit containing BOTH rules and `src/prod/app.py`
    v1 — the pre-push state every attack below tampers with."""
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    verifier_keys = {}
    for name in ("Reid", "Cyra"):
        key = verifier_gpg_keys[name]
        rel = _bundle_key(root, name, key)
        verifier_keys[name] = {"fingerprint": key.fpr, "public_key_file": rel}
    policy = _self_tamper_policy_dict(verifier_keys)
    (root / "core" / "policy" / "policy.yaml").write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod v1')\n", encoding="utf-8")

    _init_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "baseline: self-gate + prod-src rules, prod v1")
    return root


# ---------------------------------------------------------------------------
# 1) THE disclosed attack: delete BOTH rules entirely in the same commit as
#    an unreviewed payload.
# ---------------------------------------------------------------------------

def test_policy_tamper_deletes_self_gate_rule_same_push_is_blocked(tamper_repo, run_cli):
    root = tamper_repo
    base = _base_sha(root)

    policy_path = root / "core" / "policy" / "policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    # Delete the self-gating rule AND the prod-src rule entirely — the
    # sharpest version of the attack (matches the Gate Arena's own
    # attack_A3_policy_tamper_same_push exactly).
    policy["policy"]["rules"] = []
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    (root / "src" / "prod" / "app.py").write_text("print('prod v2 -- shipped via policy tamper')\n", encoding="utf-8")
    head = _commit_all(root, "chore: simplify policy config (payload hidden in same commit)")

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    # Both the policy file's own change AND the hidden payload must be
    # caught — the BASELINE's rules still require verdicts for both paths,
    # regardless of what the newly-pushed (tampered) policy now says.
    assert any("core/policy/policy.yaml" in reason for reason in payload["reasons"]), payload["reasons"]
    assert any("src/prod/app.py" in reason for reason in payload["reasons"]), payload["reasons"]
    assert any("A3 fail-closed" in reason for reason in payload["reasons"]), payload["reasons"]


# ---------------------------------------------------------------------------
# 2) Softer variant: rules kept, but globs narrowed past matching the
#    exact paths changed in this push.
# ---------------------------------------------------------------------------

def test_policy_tamper_narrows_globs_same_push_is_blocked(tamper_repo, run_cli):
    root = tamper_repo
    base = _base_sha(root)

    policy_path = root / "core" / "policy" / "policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    for rule in policy["policy"]["rules"]:
        if rule["id"] == "self-gate":
            rule["globs"] = ["core/policy/does-not-exist/**"]
        if rule["id"] == "prod-src":
            rule["globs"] = ["src/prod/does-not-exist/**"]
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    (root / "src" / "prod" / "app.py").write_text("print('prod v2 -- narrowed-glob attack')\n", encoding="utf-8")
    head = _commit_all(root, "refactor: narrow policy globs (payload hidden in same commit)")

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any("src/prod/app.py" in reason for reason in payload["reasons"]), payload["reasons"]
    assert any("core/policy/policy.yaml" in reason for reason in payload["reasons"]), payload["reasons"]


# ---------------------------------------------------------------------------
# 3) allowed_verifiers WIDENED in the same push, self-signed by the
#    newly-added name — the policy edit itself is legitimately covered
#    (isolates the mechanism under test: the widened allowed_verifiers
#    alone, not "policy.yaml has no covering verdict at all").
# ---------------------------------------------------------------------------

def test_policy_widened_allowed_verifiers_same_push_is_blocked(tamper_repo, run_cli, engine, verifier_gpg_keys):
    root = tamper_repo
    base = _base_sha(root)

    # Attacker controls a real "Quinn" identity (stand-in for a name they
    # just registered) and widens prod-src's allowed_verifiers to include
    # it — neither existed in the baseline.
    attacker_key = verifier_gpg_keys["Quinn"]
    rel = _bundle_key(root, "Quinn", attacker_key)

    policy_path = root / "core" / "policy" / "policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    policy["policy"]["verifier_keys"]["Quinn"] = {"fingerprint": attacker_key.fpr, "public_key_file": rel}
    for rule in policy["policy"]["rules"]:
        if rule["id"] == "prod-src":
            rule["allowed_verifiers"] = ["Reid", "Quinn"]
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    # Legitimately cover the policy.yaml edit itself with a genuine
    # Reid-signed verdict, isolating the test to ONLY the widened
    # allowed_verifiers mechanism.
    policy_blob = _blob_sha(root, "core/policy/policy.yaml")
    policy_verdict = _tamper_verdict(["core/policy/**"], {"core/policy/policy.yaml": policy_blob}, verifier="Reid")
    policy_verdict["signature"] = sign_verdict_for_test(engine, policy_verdict, verifier_gpg_keys["Reid"])
    _write_verdict(root, "missions/m1/verdicts/self-gate.verdict.md", policy_verdict)

    (root / "src" / "prod" / "app.py").write_text("print('prod v2 -- widened-verifier attack')\n", encoding="utf-8")
    blob = _blob_sha(root, "src/prod/app.py")
    prod_verdict = _tamper_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Quinn")
    prod_verdict["signature"] = sign_verdict_for_test(engine, prod_verdict, attacker_key)
    _write_verdict(root, "missions/m1/verdicts/prod-src.verdict.md", prod_verdict)

    head = _commit_all(root, "feat: let Quinn review prod-src too (payload hidden in same commit)")

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    # The policy.yaml edit itself is legitimately covered — it must NOT
    # appear as a violation (proves isolation of the mechanism).
    assert not any("core/policy/policy.yaml" in reason for reason in payload["reasons"]), payload["reasons"]
    # The prod-src change, "approved" only by the newly-widened Quinn, is
    # still blocked — the effective allowed_verifiers for this push is the
    # baseline∩new intersection ({Reid}), so Quinn's signature (however
    # genuinely valid) does not count.
    assert any(
        "src/prod/app.py" in reason and "allowed verifier" in reason
        for reason in payload["reasons"]
    ), payload["reasons"]


# ---------------------------------------------------------------------------
# 4) verifier_keys fingerprint SWAP in the same push — allowed_verifiers
#    untouched, only the registered key material for an already-allowed
#    name changes, and the attacker self-signs with the swapped-in key.
# ---------------------------------------------------------------------------

def test_policy_verifier_key_swap_same_push_is_blocked(tamper_repo, run_cli, engine, verifier_gpg_keys):
    root = tamper_repo
    base = _base_sha(root)

    # Attacker swaps Cyra's REGISTERED key for one they control (any other
    # real generated identity stands in for "a key the attacker controls").
    attacker_key = verifier_gpg_keys["Lysandra"]
    rel = _bundle_key(root, "Cyra", attacker_key)  # overwrites the bundled Cyra key file

    policy_path = root / "core" / "policy" / "policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    policy["policy"]["verifier_keys"]["Cyra"] = {"fingerprint": attacker_key.fpr, "public_key_file": rel}
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    policy_blob = _blob_sha(root, "core/policy/policy.yaml")
    verdict = _tamper_verdict(["core/policy/**"], {"core/policy/policy.yaml": policy_blob}, verifier="Cyra")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, attacker_key)  # "Cyra"-claimed, signed by the ATTACKER's key
    _write_verdict(root, "missions/m1/verdicts/self-gate.verdict.md", verdict)
    head = _commit_all(root, "chore: rotate Cyra's key (self-signed by the 'new' key, same push)")

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is True
    assert any(
        "core/policy/policy.yaml" in reason
        and ("does NOT match" in reason or "verification failed" in reason)
        for reason in payload["reasons"]
    ), payload["reasons"]


# ---------------------------------------------------------------------------
# 5) Regression: a genuine, non-tampering policy edit (brand-new,
#    unrelated rule added) with a REAL covering verdict still PASSES.
# ---------------------------------------------------------------------------

def test_legitimate_policy_edit_with_genuine_covering_verdict_still_passes(tamper_repo, run_cli, engine, verifier_gpg_keys):
    root = tamper_repo
    base = _base_sha(root)

    policy_path = root / "core" / "policy" / "policy.yaml"
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    policy["policy"]["rules"].append({
        "id": "docs-rule",
        "description": "newly added, unrelated rule",
        "globs": ["docs/**"],
        "classification": ["client_facing"],
        "require_verdict": True,
        "allowed_verifiers": ["Reid"],
    })
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    policy_blob = _blob_sha(root, "core/policy/policy.yaml")
    verdict = _tamper_verdict(["core/policy/**"], {"core/policy/policy.yaml": policy_blob}, verifier="Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, verifier_gpg_keys["Reid"])
    _write_verdict(root, "missions/m1/verdicts/self-gate.verdict.md", verdict)
    head = _commit_all(root, "docs: add docs-rule (genuinely reviewed policy edit)")

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False
    assert payload["reasons"] == []


# ---------------------------------------------------------------------------
# 6) Regression: an ordinary, genuinely-reviewed prod change, policy
#    entirely untouched — no false positive from the baseline-union
#    machinery when nothing in policy changed.
# ---------------------------------------------------------------------------

def test_ordinary_prod_change_unaffected_when_policy_untouched(tamper_repo, run_cli, engine, verifier_gpg_keys):
    root = tamper_repo
    base = _base_sha(root)

    (root / "src" / "prod" / "app.py").write_text("print('prod v2 -- genuinely reviewed change')\n", encoding="utf-8")
    blob = _blob_sha(root, "src/prod/app.py")
    verdict = _tamper_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Reid")
    verdict["signature"] = sign_verdict_for_test(engine, verdict, verifier_gpg_keys["Reid"])
    _write_verdict(root, "missions/m1/verdicts/prod-src.verdict.md", verdict)
    head = _commit_all(root, "prod v2 -- genuinely reviewed, policy untouched")

    r = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert payload["blocked"] is False
    assert payload["reasons"] == []
