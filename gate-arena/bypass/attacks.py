"""
gate-arena/bypass/attacks.py — the scripted bypass-attempt classes.

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
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import yaml

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
        hard_floor_reason = (
            "HARD_FLOOR_UNSATISFIED: a required hard-floor sign-off is not valid"
            in payload["reasons"]
        )

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
            f"hard_floor_code_present={hard_floor_reason} "
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
        forged_hard_floor = (
            "HARD_FLOOR_UNSATISFIED: a required hard-floor sign-off is not valid"
            in payload_forged["reasons"]
        )

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
            f"only) sign-off: blocked={forged_blocked}, hard_floor_code_present="
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


def attack_A13_protected_type_swap(base_dir: Path, engine) -> dict:
    """Protected type swaps and security-control deletions stay governed."""
    fx = _new_fixture(base_dir, engine, "A13")
    try:
        base = fx.base_sha
        (fx.root / "docs").mkdir()
        (fx.root / "docs" / "payload.py").write_text("print('ungoverned target')\n", encoding="utf-8")
        (fx.root / ".tess" / "tess.lock").write_text(
            "framework: {}\nfiles: {}\n", encoding="utf-8",
        )
        commit_all(fx.root, "add A13 baselines")
        base = head_sha(fx.root)
        protected = fx.root / "src" / "prod" / "app.py"
        protected.unlink()
        protected.symlink_to("../../docs/payload.py")
        head = commit_all(fx.root, "A13 regular-to-symlink protected type swap")
        _r, payload = fx.gate_ci(base, head)
        type_blocked = payload["blocked"]

        # Independent reverse direction from the same immutable base: Git D
        # status must not disappear from ingress. Policy + trusted-lock
        # deletion is unsatisfiable on the normal PR path.
        git(fx.root, "checkout", "-q", "-B", "a13-deletion", base)
        shutil.rmtree(fx.root / ".tess" / "trace", ignore_errors=True)
        (fx.root / "core" / "policy" / "policy.yaml").unlink()
        (fx.root / ".tess" / "tess.lock").unlink()
        deletion_head = commit_all(fx.root, "A13 delete policy and trusted lock")
        _rd, deletion_payload = fx.gate_ci(base, deletion_head)
        deletion_blocked = deletion_payload["blocked"] and (
            "SECURITY_CONTROL_DELETION: normal PR security-control deletion is not permitted"
            in deletion_payload["reasons"]
        )

        # Git's default R100 presentation names only the destination in
        # `--name-only` output. The gate disables rename collapsing so the
        # protected source becomes an explicit D and cannot disappear.
        git(fx.root, "checkout", "-q", "-B", "a13-rename", base)
        shutil.rmtree(fx.root / ".tess" / "trace", ignore_errors=True)
        git(fx.root, "mv", ".tess/tess.lock", "docs/moved-tess.lock")
        rename_head = commit_all(fx.root, "A13 rename trusted lock to ungoverned path")
        _rr, rename_payload = fx.gate_ci(base, rename_head)
        rename_blocked = rename_payload["blocked"] and (
            "SECURITY_CONTROL_DELETION: normal PR security-control deletion is not permitted"
            in rename_payload["reasons"]
        )
        blocked = type_blocked and deletion_blocked and rename_blocked
        return {
            "id": "A13",
            "name": "protected type swap, deletion, and rename",
            "description": (
                "Replace a governed regular blob with a symlink, then independently "
                "delete policy/lock controls and rename the trusted lock from the "
                "same immutable base."
            ),
            "blocked": blocked,
            "mechanism": (
                "Git reports the protected path as type-change T and control removals as D; "
                "ACDMRT --no-renames ingress includes both and refuses to hide a protected "
                "source behind an R100 destination. "
                f"Type swap blocked={type_blocked} ({payload['reasons']}); policy/lock "
                f"deletion blocked={deletion_payload['blocked']} "
                f"({deletion_payload['reasons']}); protected-source rename "
                f"blocked={rename_payload['blocked']} ({rename_payload['reasons']})."
            ),
            "evidence": {
                "type_swap_gate_result": payload,
                "control_deletion_gate_result": deletion_payload,
                "control_rename_gate_result": rename_payload,
            },
        }
    finally:
        fx.teardown()


def attack_A14_multi_push_policy_attenuation(base_dir: Path, engine) -> dict:
    """Normal push 1 cannot establish a weaker base for push 2."""
    fx = _new_fixture(base_dir, engine, "A14")
    try:
        base = fx.base_sha
        policy_path = fx.root / "core" / "policy" / "policy.yaml"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        policy["policy"]["rules"] = [
            rule for rule in policy["policy"]["rules"] if rule.get("id") != "prod-src"
        ]
        policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

        # A genuine fixture Reid approval covers the policy bytes. The A14
        # monotonic floor must still refuse attenuation; a normal verdict is
        # not a policy-epoch reset.
        policy_blob = blob_sha(fx.root, "core/policy/policy.yaml")
        verdict = base_verdict(
            ["core/policy/**"], {"core/policy/policy.yaml": policy_blob}, verifier="Reid",
        )
        verdict["signature"] = fx.sign(verdict, "Reid")
        write_verdict(fx.root, "verdicts/a14-policy.verdict.md", verdict)
        head1 = commit_all(fx.root, "A14 push 1: validly reviewed policy attenuation")
        _r1, push1 = fx.gate_ci(base, head1)

        # Counterfactual forced-land evidence: the live App-bound ruleset is
        # active, strict, and has no configured bypass, so a normal actor
        # cannot do this. If a repository owner first changes/defeats that
        # external control and forcibly makes head1 the base, the second
        # payload is no longer covered. This is why hostile-owner resistance
        # is outside the deterministic corpus and the future external
        # epoch-reset authority remains part of closure.
        (fx.root / "src" / "prod" / "app.py").write_text(
            "print('A14 push 2 unreviewed payload')\n", encoding="utf-8",
        )
        head2 = commit_all(fx.root, "A14 push 2: exploit attenuated base")
        _r2, forced_push2 = fx.gate_ci(head1, head2)

        blocked = push1["blocked"] is True
        return {
            "id": "A14",
            "name": "multi-push policy attenuation",
            "description": (
                "Use a genuinely signed policy-review verdict in push 1 to remove a rule, "
                "then exploit the weaker base in push 2."
            ),
            "blocked": blocked,
            "mechanism": (
                f"Normal push 1 was {'BLOCKED' if push1['blocked'] else 'NOT BLOCKED'} even "
                "with a valid fixture signature because attenuation requires an external "
                f"policy epoch ({push1['reasons']}). The live ruleset is active, strict, "
                "App-bound, and has no configured bypass. Counterfactual only after an "
                "owner first changes/defeats that external rule and forces push 1 to land: "
                f"push 2 blocked={forced_push2['blocked']}. The external epoch-reset path "
                "is not implemented."
            ),
            "evidence": {
                "normal_push1": push1,
                "forced_land_push2_counterfactual": forced_push2,
                "complete_production_closure": False,
            },
        }
    finally:
        fx.teardown()


def attack_A15_multi_push_trust_registry_bootstrap(base_dir: Path, engine) -> dict:
    """A normal push cannot install authority that becomes trusted at next BASE."""
    fx = _new_fixture(base_dir, engine, "A15")
    try:
        base = fx.base_sha
        policy_path = fx.root / "core" / "policy" / "policy.yaml"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        # Rotate Quinn's registered authority to Cyra's already-valid fixture
        # public key. No new key is generated: if this normal PR landed, a
        # later verdict claiming Quinn but signed by Cyra would verify from
        # the new BASE.
        policy["policy"]["verifier_keys"]["Quinn"] = dict(
            policy["policy"]["verifier_keys"]["Cyra"]
        )
        policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

        policy_blob = blob_sha(fx.root, "core/policy/policy.yaml")
        policy_verdict = base_verdict(
            ["core/policy/**"], {"core/policy/policy.yaml": policy_blob}, verifier="Reid",
        )
        policy_verdict["signature"] = fx.sign(policy_verdict, "Reid")
        write_verdict(fx.root, "verdicts/a15-policy.verdict.md", policy_verdict)
        head1 = commit_all(
            fx.root, "A15 push 1: validly reviewed verifier authority rotation",
        )
        _r1, push1 = fx.gate_ci(base, head1)

        # Counterfactual forced land: prove the registry delta is not merely
        # cosmetic. From head1 as BASE, Cyra's fixture private key can now
        # authenticate a verdict that claims Quinn, the verifier allowed by
        # prod-src. The live external rule prevents this forced land in the
        # normal path; the pass below is disclosed, not counted as a slip.
        (fx.root / "src" / "prod" / "app.py").write_text(
            "print('A15 push 2 via rotated authority')\n", encoding="utf-8",
        )
        app_blob = blob_sha(fx.root, "src/prod/app.py")
        payload_verdict = base_verdict(
            ["src/prod/**"], {"src/prod/app.py": app_blob}, verifier="Quinn",
        )
        payload_verdict["signature"] = fx.sign(payload_verdict, "Cyra")
        write_verdict(fx.root, "verdicts/a15-payload.verdict.md", payload_verdict)
        head2 = commit_all(fx.root, "A15 push 2: use rotated verifier authority")
        _r2, forced_push2 = fx.gate_ci(head1, head2)

        blocked = push1["blocked"] and (
            "POLICY_EPOCH_RESET_REQUIRED: normal PR policy attenuation is not permitted"
            in push1["reasons"]
        ) and forced_push2["blocked"] is False and forced_push2.get("reasons") == []
        return {
            "id": "A15",
            "name": "multi-push trust-registry bootstrap",
            "description": (
                "Rotate a verifier trust anchor in push 1 so a later push "
                "could inherit attacker-selected authority from BASE."
            ),
            "blocked": blocked,
            "mechanism": (
                f"Normal push 1 was {'BLOCKED' if push1['blocked'] else 'NOT BLOCKED'}: "
                f"{push1['reasons']}. Any verifier_keys or signoff_keys delta requires "
                "an external policy epoch; no in-band reset or candidate trust bootstrap exists. "
                "Counterfactual after an owner defeats the external rule and forces push 1 "
                f"to land: rotated-authority push 2 blocked={forced_push2['blocked']}."
            ),
            "evidence": {
                "normal_push1": push1,
                "forced_land_rotated_authority_push2_counterfactual": forced_push2,
                "new_key_generated": False,
                "complete_production_closure": False,
            },
        }
    finally:
        fx.teardown()


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
    attack_A13_protected_type_swap,
    attack_A14_multi_push_policy_attenuation,
    attack_A15_multi_push_trust_registry_bootstrap,
]
