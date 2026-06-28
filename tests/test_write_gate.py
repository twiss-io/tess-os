"""
Write-gate: allowlist + path-containment.

Ports the scratchpad adversarial harness (gate_test_r3.py) into proper tests:
traversal / absolute / .git / .local.md / never_touch are DENIED; legitimate
owned paths are ALLOWED. Plus a real-symlink directory-component containment test.
"""

from __future__ import annotations

import json
import shutil

import pytest

from conftest import MANIFEST_SRC

DENY = "DENY"
ALLOW = "ALLOW"

# (path, expected, description) — ported verbatim from gate_test_r3.py
GATE_CASES = [
    # C1 tree-escape via ../
    ("../../../../etc/passwd", DENY, "tree-escape ../../../../"),
    ("../../.ssh/authorized_keys", DENY, "tree-escape ../../"),
    ("conductor/guardrails.md/../../.env", DENY, "owned-prefix then escape to .env"),
    ("clients/_template/../ExampleClient/secret.md", DENY, "owned _template then escape"),
    ("agents/../.env", DENY, "agents -> .env"),
    ("agents/../kb/wiki/poisoned.md", DENY, "agents -> kb/"),
    ("agents/../operator/identity-stub.md", DENY, "agents -> operator/"),
    ("agents/../clients/ExampleClient/secret.md", DENY, "agents -> clients/"),
    ("agents/../.claude/settings.local.json", DENY, "agents -> settings.local.json"),
    (".claude/agents/../../conductor/guardrails.local.md", DENY, ".claude/agents -> .local.md"),
    ("conductor/x/../guardrails.local.md", DENY, "conductor sub -> .local.md"),
    # C1 absolute paths
    ("/etc/passwd", DENY, "absolute /etc/passwd"),
    ("/tmp/evil.md", DENY, "absolute /tmp/evil.md"),
    # C1 .git RCE sink — top-level
    (".git/hooks/post-checkout", DENY, ".git RCE post-checkout"),
    (".git/hooks/pre-commit", DENY, ".git RCE pre-commit"),
    (".git/config", DENY, ".git RCE config"),
    (".git", DENY, ".git bare"),
    # nested + case-insensitive .git
    ("agents/sub/.git/hooks/x", DENY, "nested .git"),
    ("conductor/proj/.git/config", DENY, "nested .git config"),
    (".GIT/hooks/post-checkout", DENY, "case-insensitive .GIT"),
    (".Git/config", DENY, "case-insensitive .Git"),
    ("agents/.GIT/hooks/pre-commit", DENY, "nested case-insensitive .GIT"),
    # ALLOWLIST: neither owned nor never
    ("Makefile", DENY, "Makefile not in owned_globs"),
    ("newfile-not-listed.md", DENY, "random file not in owned"),
    ("./clients/ExampleClient/x.md", DENY, "normalizes to non-owned"),
    # never_touch paths (not in owned)
    ("clients/ExampleClient/secret.md", DENY, "never_touch clients/*/**"),
    ("kb/wiki/x.md", DENY, "never_touch kb/**"),
    ("operator/identity.md", DENY, "never_touch operator/**"),
    (".env", DENY, "never_touch .env"),
    (".env.production", DENY, "never_touch .env.*"),
    (".claude/settings.local.json", DENY, "never_touch settings.local.json"),
    # .local.md hard guard — canonical lowercase
    ("conductor/guardrails.local.md", DENY, "canonical .local.md in owned conductor/**"),
    ("clients/ExampleClient/x.local.md", DENY, ".local.md in non-owned path"),
    (".claude/hooks/my-custom.local.md", DENY, ".local.md in owned .claude/hooks/**"),
    # case-variant .local.md — must ALL deny
    ("conductor/guardrails.LOCAL.md", DENY, "case-bypass .LOCAL.md"),
    ("conductor/guardrails.Local.md", DENY, "case-bypass .Local.md"),
    ("conductor/guardrails.local.MD", DENY, "case-bypass .local.MD"),
    (".claude/hooks/x.LOCAL.MD", DENY, "case-bypass .LOCAL.MD"),
    ("agents/leah/notes.Local.Md", DENY, "case-bypass .Local.Md"),
    ("CLAUDE.LOCAL.MD", DENY, "case-bypass CLAUDE.LOCAL.MD"),
    # trailing-dot component (Windows-class poison)
    ("conductor/guardrails.local.md.", DENY, "trailing-dot .local.md."),
    # LEGITIMATE owned paths — MUST ALLOW
    ("agents/leah/README.md", ALLOW, "owned agents/**"),
    ("conductor/guardrails.md", ALLOW, "owned conductor/** (security tier)"),
    ("conductor/dispatch-brief.md", ALLOW, "owned conductor/** (security tier)"),
    ("conductor/verification-routing.md", ALLOW, "owned conductor/**"),
    ("CLAUDE.md", ALLOW, "CLAUDE.md exact"),
    (".claude/settings.json", ALLOW, ".claude/settings.json exact"),
    (".claude/agents/some-agent.md", ALLOW, ".claude/agents/**"),
    (".claude/commands/wake.md", ALLOW, ".claude/commands/**"),
    (".claude/hooks/dispatch-guard.sh", ALLOW, ".claude/hooks/**"),
    (".claude/skills/some-skill/README.md", ALLOW, ".claude/skills/**"),
    ("clients/_template/CLAUDE.md", ALLOW, "clients/_template/** (owned beats never)"),
    ("clients/_template/kb/raw/notes.md", ALLOW, "clients/_template/** deep path"),
]


@pytest.fixture
def gate_root(tmp_path):
    shutil.copy2(MANIFEST_SRC, tmp_path / "tess.manifest.json")
    return tmp_path


@pytest.fixture
def manifest():
    return json.loads(MANIFEST_SRC.read_text())


@pytest.mark.parametrize("path,expected,desc", GATE_CASES,
                         ids=[f"{e}:{d}" for _, e, d in GATE_CASES])
def test_gate_case(engine, gate_root, manifest, path, expected, desc):
    if expected == ALLOW:
        norm = engine.check_manifest_write_gate(gate_root, manifest, path, op="test")
        assert isinstance(norm, str) and norm
    else:
        with pytest.raises(engine.GateError):
            engine.check_manifest_write_gate(gate_root, manifest, path, op="test")


def test_gate_denies_symlink_directory_component(engine, gate_root, manifest):
    """A real symlink directory component in an owned path is rejected (TOCTOU)."""
    (gate_root / "kb").mkdir()
    (gate_root / "conductor").mkdir()
    # conductor/linked -> ../kb (escapes into a never_touch zone via symlink)
    (gate_root / "conductor" / "linked").symlink_to(gate_root / "kb")
    with pytest.raises(engine.GateError) as ei:
        engine.check_manifest_write_gate(
            gate_root, manifest, "conductor/linked/poison.md", op="test")
    assert "symlink" in str(ei.value).lower() or "outside" in str(ei.value).lower()


def test_gate_returns_normalized_relpath(engine, gate_root, manifest):
    # Leading './' is normalized away (literal '..' is denied outright, so it
    # cannot be used to demonstrate normalization).
    norm = engine.check_manifest_write_gate(
        gate_root, manifest, "./conductor/guardrails.md", op="test")
    assert norm == "conductor/guardrails.md"


def test_gate_owned_beats_never_for_template(engine, gate_root, manifest):
    """precedence: owned_globs WINS over never_touch (clients/_template/**)."""
    norm = engine.check_manifest_write_gate(
        gate_root, manifest, "clients/_template/admin/notes.md", op="test")
    assert norm == "clients/_template/admin/notes.md"


# ---------------------------------------------------------------------------
# M5 hardening — poisoned-manifest probe for .local.md hard guard
#
# Cyra-found bypass: under a fully-poisoned manifest (never_touch:[], owned_globs:
# ['**']) the previous manifest-dependent check (local_guard = [g for g in
# effective_never if g in LOCAL_MD_GUARD]) returned [] and x.local.md was ALLOWED.
# The guard is now hardcoded (Step 3c), same tier as .git and vault — it fires
# regardless of manifest contents.  These tests prove the promoted guard works
# under a poisoned manifest that grants full ownership and clears never_touch.
# ---------------------------------------------------------------------------

_POISONED_MANIFEST = {
    "owned_globs": ["**"],    # everything claimed as owned
    "never_touch": [],        # no never_touch entries — *.local.md is ABSENT
}

# Each of these MUST be denied even under the poisoned manifest.
_POISONED_LOCAL_MD_CASES = [
    ("x.local.md",                        "bare root .local.md"),
    ("conductor/guardrails.local.md",      "conductor/* .local.md — key Cyra case"),
    ("a/b/C.LOCAL.MD",                     "deep nested case-variant .LOCAL.MD"),
    ("x.local.md.",                        "trailing-dot Windows-class poison"),
]

# These paths SHOULD be ALLOWED under the poisoned manifest (proving the guard
# is scoped to .local.md only and does not over-block).
_POISONED_ALLOWED_CASES = [
    ("conductor/guardrails.md",    "canonical .md — NOT .local.md"),
    ("agents/leah/README.md",      "normal agent file"),
    ("CLAUDE.md",                  "root CLAUDE.md"),
]


@pytest.mark.parametrize("path,desc", _POISONED_LOCAL_MD_CASES,
                         ids=[d for _, d in _POISONED_LOCAL_MD_CASES])
def test_local_md_hardcoded_guard_fires_under_poisoned_manifest(
        engine, gate_root, path, desc):
    """
    .local.md guard is HARDCODED — fires regardless of manifest contents.

    A poisoned manifest with never_touch:[] and owned_globs:['**'] bypassed
    the previous manifest-dependent check.  The promoted Step 3c guard must
    deny these paths unconditionally.
    """
    with pytest.raises(engine.GateError) as ei:
        engine.check_manifest_write_gate(
            gate_root, _POISONED_MANIFEST, path, op="test")
    err = str(ei.value)
    assert "local.md" in err.lower()
    assert "hard guard" in err.lower() or "hardcoded" in err.lower() or "refused" in err.lower()


@pytest.mark.parametrize("path,desc", _POISONED_ALLOWED_CASES,
                         ids=[d for _, d in _POISONED_ALLOWED_CASES])
def test_local_md_guard_does_not_over_block_normal_paths_under_poisoned_manifest(
        engine, gate_root, path, desc):
    """
    Normal .md files must still be ALLOWED under the poisoned manifest.
    The guard is scoped to paths whose normalized final component ends in '.local.md'.
    """
    norm = engine.check_manifest_write_gate(
        gate_root, _POISONED_MANIFEST, path, op="test")
    assert isinstance(norm, str) and norm
