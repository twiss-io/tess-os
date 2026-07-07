"""
gate-arena/bypass/attacks.py — the 10 scripted bypass-attempt classes.

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
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from lib import (
    FixtureRepo, base_verdict, blob_sha, commit_all, git, head_sha,
    run_cli, write_signoff, write_verdict,
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

        # Prove the mechanism isn't just permanently bricked: a REAL human
        # sign-off artifact (the only thing that CAN clear a hard floor)
        # does clear it.
        write_signoff(fx.root, "credentials", "credentials", "Xavier-authorized rotation, simulated for arena.")
        head2 = commit_all(fx.root, "add human sign-off artifact for credentials hard floor")
        r2, payload2 = fx.gate_ci(base2, head2)
        clears_with_real_signoff = not payload2["blocked"]

        mechanism = (
            f"hard-floor 'credentials' rule matched config.env; a fully valid, correctly-signed "
            f"Quinn APPROVE verdict was NOT sufficient — blocked={blocked_without_signoff}, "
            f"hard_floor_reason_present={hard_floor_reason} "
            f"({payload['reasons']}). With a real .tess/gate/signoffs/credentials.signoff.json "
            f"artifact added, the SAME change clears (blocked={payload2['blocked']}) — proving "
            f"this is a real escape valve (human sign-off), not the hard floor being permanently unusable."
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

    # (c) expired signing key — tested empirically. Generate Quinn's key
    # with Expire-Date already in the past, sign honestly, see what
    # _gate_verify_verdict_signature actually does (it is read to check
    # VALIDSIG + fingerprint equality only — does it also require GOODSIG /
    # reject EXPKEYSIG? Find out by running it, not by assuming).
    fx = _new_fixture(base_dir, engine, "A10c")
    try:
        from lib import gen_verifier_key, bundle_key, kill_gpg_agent
        expired_key = gen_verifier_key("Quinn", fx.gpg_base, expire="20200101")
        # Re-bundle Quinn's PUBLIC key + fingerprint with the EXPIRED identity.
        rel = bundle_key(fx.root, "Quinn", expired_key)
        import yaml
        policy_path = fx.root / "core" / "policy" / "policy.yaml"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        policy["policy"]["verifier_keys"]["Quinn"] = {"fingerprint": expired_key.fpr, "public_key_file": rel}
        policy_path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
        commit_all(fx.root, "register an EXPIRED Quinn key (Expire-Date: 2020-01-01)")
        base2 = head_sha(fx.root)

        (fx.root / "src" / "prod" / "app.py").write_text("print('prod v2')\n", encoding="utf-8")
        blob = blob_sha(fx.root, "src/prod/app.py")
        verdict = base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Quinn")
        verdict["signature"] = fx.sign_expired(verdict, expired_key) if hasattr(fx, "sign_expired") else _sign_with(engine, verdict, expired_key)
        write_verdict(fx.root, "verdicts/prod-src.verdict.md", verdict)
        head = commit_all(fx.root, "prod change + verdict signed with an ALREADY-EXPIRED key")
        r, payload = fx.gate_ci(base2, head)
        blocked = payload["blocked"]
        results["expired_key"] = {
            "blocked": blocked,
            "reasons": payload["reasons"],
            "note": (
                "the key's Expire-Date (2020-01-01) is already in the past at signing AND "
                "verification time; `_gate_verify_verdict_signature` / `_parse_gpg_fingerprint` "
                "only parse gpg's VALIDSIG status line and check fingerprint equality — they do "
                "not inspect gpg's EXPKEYSIG/KEYEXPIRED classification at all. Empirically: "
                + ("gate BLOCKED it anyway (see reasons/exit code — gpg's own exit code or output shape must be doing more than the code comments suggest)."
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
]
