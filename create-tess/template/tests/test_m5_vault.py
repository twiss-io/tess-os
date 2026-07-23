"""
M5 vault subsystem — age-encrypted secret store + `tessctl vault` CLI.

Covers the six scenarios in the M5 build report plus the security invariants
the report relies on:

  1. set/get/list/rm round-trip — value stored ENCRYPTED at rest (the .age blob
     does NOT contain the plaintext); list and masked-get never expose the value.
  2. `vault exec --ref X [--as VAR] -- <cmd>` — JIT injection: the child sees the
     value in its env, but tessctl's own stdout/stderr never emit the plaintext.
  3. HARD-GUARD — render/restore/capture/publish/guarded_write of any vault path
     is REFUSED by the manifest write gate, the same tier as `.git`; owned_globs
     cannot override it. The two committable scaffold paths are exempt.
  4. The vault blob + identity + recipients are gitignored (`git check-ignore`)
     and listed in `.npmignore`.
  5. rotate re-encrypts a new value (old value gone, new value retrievable); a
     non-matching identity cannot decrypt the recipient-bound blob.
  6. A fresh instance ships with NO vault secrets (empty), and the public repo
     tracks only the value-free scaffold (.gitkeep + vault.registry.json).

Identity custody in tests uses the TESS_VAULT_IDENTITY env var (resolution
priority 1) so the suite NEVER touches the real macOS keychain or the user's
~/.config/tess/vault/ home directory.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import types

import pytest

from conftest import MANIFEST_SRC, REPO_ROOT, Project

# ---------------------------------------------------------------------------
# Backend / tool availability — pyrage (pip) preferred, age/rage CLI fallback.
# ---------------------------------------------------------------------------

def _have_backend() -> bool:
    try:
        import pyrage  # noqa: F401
        return True
    except ImportError:
        return shutil.which("age") is not None or shutil.which("rage") is not None


HAS_BACKEND = _have_backend()
HAS_GIT = shutil.which("git") is not None

# In CI, a missing backend is a configuration error — the vault test suite
# must not silently skip in the environment that gates releases.
# pyrage is declared in requirements-dev.txt; if it is absent in CI, the job
# should fail loudly so the gap is visible, not masked by green skips.
if not HAS_BACKEND and os.environ.get("CI"):
    pytest.fail(
        "M5 vault: no age crypto backend in CI. "
        "Install pyrage: pip install pyrage>=1.1  (declared in requirements-dev.txt). "
        "All 48 vault tests would skip without this, voiding the release quality gate.",
        pytrace=False,
    )

pytestmark = pytest.mark.skipif(
    not HAS_BACKEND,
    reason="no age crypto backend (pip install pyrage, or brew install age)",
)


# ---------------------------------------------------------------------------
# Vault fixture — a synthetic project with a real, recipient-bound identity.
# ---------------------------------------------------------------------------

@pytest.fixture
def vault(project, engine, monkeypatch):
    """A project with .claude/vault/ scaffolded and an env-custody identity.

    Generates a genuine age X25519 keypair, writes vault.recipients (public key),
    seeds the value-free registry scaffold, and exports the private key via
    TESS_VAULT_IDENTITY (priority-1 custody) for both in-process and subprocess
    calls. No keychain, no home-dir writes.
    """
    root = project.root
    backend = engine._vault_check_crypto()
    priv, pub = engine._vault_generate_identity(backend)

    vdir = root / ".claude" / "vault"
    vdir.mkdir(parents=True, exist_ok=True)
    os.chmod(vdir, 0o700)
    (vdir / "vault.recipients").write_text(
        f"# age public key for this vault\n{pub}\n", encoding="utf-8"
    )
    engine._vault_write_registry_scaffold(root)

    monkeypatch.setenv("TESS_VAULT_IDENTITY", priv)

    return types.SimpleNamespace(
        root=root, priv=priv, pub=pub, backend=backend,
        env={"TESS_VAULT_IDENTITY": priv}, project=project, engine=engine,
    )


SECRET = "ghp_TESTtoken1234567890ABCDEFGHIJ0001"  # GitHub-token-shaped, len > 6


# ===========================================================================
# Pure helpers — ref parsing + value masking
# ===========================================================================

@pytest.mark.parametrize("ref,expected", [
    ("github/token", ("github", "token")),
    ("vault://github/token", ("github", "token")),     # vault:// prefix stripped
    ("anthropic/api_key", ("anthropic", "api_key")),
    ("a.b-c/d_e.f", ("a.b-c", "d_e.f")),
])
def test_parse_ref_valid(engine, ref, expected):
    assert engine._vault_parse_ref(ref) == expected


@pytest.mark.parametrize("ref", [
    "nogithub",          # no slash
    "github/",           # empty key
    "/token",            # empty service
    "../token",          # traversal-like service
    "github/..",         # traversal-like key
    "vault://../token",  # traversal-like service with public prefix
    "vault://github/token/extra",  # more than service/key
    "bad service/key",   # space (invalid char)
    "svc/k$y",           # invalid char
])
def test_parse_ref_invalid_exits(engine, ref):
    with pytest.raises(SystemExit):
        engine._vault_parse_ref(ref)


@pytest.mark.parametrize("ref", ["github/token", "vault://github/token"])
def test_canonical_ref_has_one_storage_spelling(engine, ref):
    assert engine._vault_canonical_ref(ref) == "github/token"


def test_mask_value_short_is_all_dots(engine):
    masked = engine._vault_mask_value("abc", "svc/k")
    assert "abc" not in masked
    assert set(masked) == {"•"}  # all bullet characters


def test_mask_value_long_hides_middle(engine):
    masked = engine._vault_mask_value(SECRET, "github/token")
    assert SECRET not in masked          # full value never present
    assert masked.startswith("ghp_")     # short prefix shown
    assert SECRET[-4:] in masked         # short suffix shown
    assert "•" * 8 in masked        # masked middle
    # the sensitive middle section is absent
    assert SECRET[4:-4] not in masked


# ===========================================================================
# (1) set / get / list / rm round-trip + encrypted-at-rest
# ===========================================================================

def test_set_get_list_rm_roundtrip(vault, run_cli):
    root = vault.root
    r = run_cli(root, "vault", "set", "test/secret",
                input_text=SECRET + "\n", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "stored" in r.stdout
    assert SECRET not in r.stdout  # confirmation never echoes the value

    # masked get
    r = run_cli(root, "vault", "get", "test/secret", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert SECRET not in r.stdout
    assert "•" in r.stdout

    # reveal (captured stdout is a pipe, not a TTY → allowed) returns raw value
    r = run_cli(root, "vault", "get", "test/secret", "--reveal", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert r.stdout == SECRET

    # list shows the ref + service but never the value
    r = run_cli(root, "vault", "list", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "test/secret" in r.stdout
    assert "test" in r.stdout
    assert SECRET not in r.stdout

    # rm removes the entry
    r = run_cli(root, "vault", "rm", "test/secret", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "removed" in r.stdout

    # gone
    r = run_cli(root, "vault", "get", "test/secret", extra_env=vault.env)
    assert r.returncode != 0
    assert "not found" in (r.stdout + r.stderr).lower()


def test_value_encrypted_at_rest(vault, run_cli, engine):
    root = vault.root
    r = run_cli(root, "vault", "set", "test/secret",
                input_text=SECRET + "\n", extra_env=vault.env)
    assert r.returncode == 0, r.stderr

    blob_path = root / ".claude" / "vault" / "vault.age"
    raw = blob_path.read_bytes()
    # The blob is age-armored ciphertext, NOT the plaintext.
    assert raw.startswith(b"-----BEGIN AGE ENCRYPTED FILE-----")
    assert SECRET.encode() not in raw
    assert b"test/secret" not in raw  # even the ref name is inside the ciphertext

    # blob perms are 0600
    assert stat.S_IMODE(blob_path.stat().st_mode) == 0o600

    # but decrypting with the matching identity recovers the exact value
    data = engine._vault_read_blob(root)
    assert data["entries"]["test/secret"]["value"] == SECRET


def test_set_value_not_accepted_on_argv(vault, run_cli):
    """`vault set` exposes no value argument — the value can only come from
    stdin/TTY, never argv (which would leak to `ps`/shell history)."""
    r = run_cli(root := vault.root, "vault", "set", "test/secret", "EXTRA_ARG",
                extra_env=vault.env)
    assert r.returncode == 2  # argparse rejects the extra positional
    assert "unrecognized arguments" in r.stderr.lower()


def test_set_empty_value_rejected(vault, run_cli):
    r = run_cli(vault.root, "vault", "set", "test/secret",
                input_text="\n", extra_env=vault.env)
    assert r.returncode != 0
    assert "empty" in (r.stdout + r.stderr).lower()


def test_prefixed_and_canonical_refs_share_one_new_storage_entry(vault, run_cli, engine):
    """The public vault:// spelling cannot create a second encrypted entry."""
    root = vault.root
    r = run_cli(root, "vault", "set", "vault://test/secret",
                input_text=SECRET + "\n", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert SECRET not in r.stdout + r.stderr

    data = engine._vault_read_blob(root)
    assert set(data["entries"]) == {"test/secret"}

    # Both references resolve the same stored value, with masked CLI output.
    for ref in ("test/secret", "vault://test/secret"):
        r = run_cli(root, "vault", "get", ref, extra_env=vault.env)
        assert r.returncode == 0, r.stderr
        assert "test/secret" in r.stdout
        assert SECRET not in r.stdout + r.stderr

    r = run_cli(root, "vault", "list", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "test/secret" in r.stdout
    assert "vault://test/secret" not in r.stdout
    assert SECRET not in r.stdout + r.stderr

    # The default exec env name derives from the canonical ref, never vault://.
    r = run_cli(root, "vault", "exec", "--ref", "vault://test/secret", "--",
                sys.executable, "-c", _CHILD_WRITE.format(var="TEST_SECRET"),
                extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert (root / "child_out.txt").read_text() == SECRET
    assert SECRET not in r.stdout + r.stderr

    r = run_cli(root, "vault", "rotate", "vault://test/secret",
                input_text="ROTATED_value_not_printed_12345\n", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "ROTATED_value_not_printed_12345" not in r.stdout + r.stderr
    assert set(engine._vault_read_blob(root)["entries"]) == {"test/secret"}

    r = run_cli(root, "vault", "rm", "vault://test/secret", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "removed test/secret" in r.stdout
    assert SECRET not in r.stdout + r.stderr


def _seed_legacy_prefixed_entry(vault, engine, value=SECRET):
    """Seed the raw-key format emitted by the first vault implementation."""
    data = {
        "version": 1,
        "entries": {
            "vault://legacy/secret": {
                "value": value,
                "meta": {"service": "legacy", "key": "secret", "minted_at": "test"},
            }
        }
    }
    engine._vault_write_blob(vault.root, data)


def test_legacy_prefixed_entry_reads_safely_then_requires_explicit_migration(vault, run_cli, engine):
    """Old prefixed keys remain usable, but normalization is never automatic."""
    _seed_legacy_prefixed_entry(vault, engine)

    r = run_cli(vault.root, "vault", "get", "legacy/secret", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "legacy/secret" in r.stdout
    assert SECRET not in r.stdout + r.stderr

    r = run_cli(vault.root, "vault", "list", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "legacy/secret" in r.stdout
    assert "vault://legacy/secret" not in r.stdout
    assert SECRET not in r.stdout + r.stderr

    # A default migration run is dry-run only: the old encrypted key remains.
    r = run_cli(vault.root, "vault", "migrate-refs", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "dry run" in r.stdout
    assert "vault://legacy/secret" in r.stdout
    assert SECRET not in r.stdout + r.stderr
    assert set(engine._vault_read_blob(vault.root)["entries"]) == {"vault://legacy/secret"}
    plan_match = re.search(r"plan id: ([0-9a-f]{16})", r.stdout)
    assert plan_match, r.stdout

    # An apply without a dry-run plan token cannot change the encrypted blob.
    r = run_cli(vault.root, "vault", "migrate-refs", "--apply", extra_env=vault.env)
    assert r.returncode != 0
    assert "dry-run plan id" in (r.stdout + r.stderr)
    assert SECRET not in r.stdout + r.stderr
    assert set(engine._vault_read_blob(vault.root)["entries"]) == {"vault://legacy/secret"}

    # Only explicit --apply changes the key; the entry's value/metadata survive.
    r = run_cli(vault.root, "vault", "migrate-refs", "--apply", "--plan", plan_match.group(1),
                extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "normalized 1" in r.stdout
    assert SECRET not in r.stdout + r.stderr
    data = engine._vault_read_blob(vault.root)
    assert set(data["entries"]) == {"legacy/secret"}
    assert data["entries"]["legacy/secret"]["value"] == SECRET


def test_duplicate_canonical_and_legacy_refs_fail_closed_without_value_output(vault, run_cli, engine):
    """The resolver must not guess which of two differently-valued entries wins."""
    canonical_value = "CANONICAL_value_not_to_be_printed_12345"
    legacy_value = "LEGACY_value_not_to_be_printed_67890"
    engine._vault_write_blob(vault.root, {
        "version": 1,
        "entries": {
            "test/secret": {"value": canonical_value, "meta": {}},
            "vault://test/secret": {"value": legacy_value, "meta": {}},
        }
    })

    for command in (
        ("get", "test/secret"),
        ("exec", "--ref", "vault://test/secret", "--", sys.executable, "-c", "print('unreachable')"),
        ("list",),
        ("migrate-refs", "--apply"),
    ):
        r = run_cli(vault.root, "vault", *command, extra_env=vault.env)
        assert r.returncode != 0
        assert "ambiguous" in (r.stdout + r.stderr).lower()
        assert canonical_value not in r.stdout + r.stderr
        assert legacy_value not in r.stdout + r.stderr

    # Refusal leaves both possible secrets untouched for owner-led recovery.
    assert set(engine._vault_read_blob(vault.root)["entries"]) == {
        "test/secret", "vault://test/secret"
    }


def test_incompatible_legacy_path_is_denied_without_migration_or_value_output(vault, run_cli, engine):
    """Malformed old map keys are visible as a recovery problem, never guessed."""
    value = "INVALID_path_value_not_to_be_printed_12345"
    engine._vault_write_blob(vault.root, {
        "version": 1,
        "entries": {"vault://../secret": {"value": value, "meta": {}}}
    })

    r = run_cli(vault.root, "vault", "migrate-refs", "--apply", extra_env=vault.env)
    assert r.returncode != 0
    assert "invalid stored ref" in (r.stdout + r.stderr).lower()
    assert value not in r.stdout + r.stderr
    assert set(engine._vault_read_blob(vault.root)["entries"]) == {"vault://../secret"}

    r = run_cli(vault.root, "vault", "get", "vault://../secret", extra_env=vault.env)
    assert r.returncode != 0
    assert value not in r.stdout + r.stderr


def test_recover_exact_stored_ref_preserves_owner_access_without_auto_selection(vault, run_cli, engine):
    """Duplicates and dot components remain recoverable only by exact key."""
    canonical_value = "CANONICAL_recovery_value_not_printed_12345"
    legacy_value = "LEGACY_recovery_value_not_printed_67890"
    dot_value = "DOT_recovery_value_not_printed_ABCDE"
    engine._vault_write_blob(vault.root, {
        "version": 1,
        "entries": {
            "test/secret": {"value": canonical_value, "meta": {}},
            "vault://test/secret": {"value": legacy_value, "meta": {}},
            "vault://dot/..": {"value": dot_value, "meta": {}},
        },
    })

    # Normal canonical resolution remains fail-closed; it cannot choose a value.
    r = run_cli(vault.root, "vault", "get", "test/secret", extra_env=vault.env)
    assert r.returncode != 0
    assert "ambiguous" in (r.stdout + r.stderr).lower()
    assert canonical_value not in r.stdout + r.stderr
    assert legacy_value not in r.stdout + r.stderr

    # Recovery reads *exactly* the owner-selected map key and remains masked.
    for stored_ref, value in (
        ("test/secret", canonical_value),
        ("vault://test/secret", legacy_value),
        ("vault://dot/..", dot_value),
    ):
        r = run_cli(vault.root, "vault", "recover", "get", stored_ref, extra_env=vault.env)
        assert r.returncode == 0, r.stderr
        assert value not in r.stdout + r.stderr
        assert "recovery mode" in r.stdout

    # Exact recovery exec provides a no-output way to validate each candidate.
    for stored_ref, value in (
        ("test/secret", canonical_value),
        ("vault://test/secret", legacy_value),
        ("vault://dot/..", dot_value),
    ):
        r = run_cli(vault.root, "vault", "recover", "exec", "--stored-ref", stored_ref,
                    "--as", "RECOVERED_SECRET", "--", sys.executable, "-c",
                    _CHILD_WRITE.format(var="RECOVERED_SECRET"), extra_env=vault.env)
        assert r.returncode == 0, r.stderr
        assert (vault.root / "child_out.txt").read_text() == value
        assert value not in r.stdout + r.stderr

    # Only an explicit exact-key removal resolves the duplicate; no command
    # silently selected or deleted either entry before this owner action.
    r = run_cli(vault.root, "vault", "recover", "rm", "vault://test/secret", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert legacy_value not in r.stdout + r.stderr
    data = engine._vault_read_blob(vault.root)
    assert set(data["entries"]) == {"test/secret", "vault://dot/.."}
    assert data["entries"]["test/secret"]["value"] == canonical_value

    r = run_cli(vault.root, "vault", "get", "test/secret", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert canonical_value not in r.stdout + r.stderr


def test_migration_plan_rejects_ciphertext_changed_after_dry_run(vault, run_cli, engine):
    """A plan ID is tied to the exact age ciphertext, not merely ref names."""
    _seed_legacy_prefixed_entry(vault, engine)
    r = run_cli(vault.root, "vault", "migrate-refs", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    plan_id = re.search(r"plan id: ([0-9a-f]{16})", r.stdout).group(1)

    newer_value = "NEWER_mutation_value_not_to_be_printed_12345"
    r = run_cli(vault.root, "vault", "set", "other/secret", input_text=newer_value + "\n",
                extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert newer_value not in r.stdout + r.stderr

    r = run_cli(vault.root, "vault", "migrate-refs", "--apply", "--plan", plan_id,
                extra_env=vault.env)
    assert r.returncode != 0
    assert "stale" in (r.stdout + r.stderr).lower()
    assert SECRET not in r.stdout + r.stderr
    assert newer_value not in r.stdout + r.stderr
    assert set(engine._vault_read_blob(vault.root)["entries"]) == {
        "vault://legacy/secret", "other/secret"
    }


def _write_unvalidated_blob(vault, engine, payload):
    """Test-only writer for ciphertext that deliberately bypasses schema checks."""
    plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ciphertext = engine._vault_encrypt(vault.backend, plaintext, vault.pub)
    blob_path = vault.root / ".claude" / "vault" / "vault.age"
    blob_path.write_bytes(ciphertext)
    os.chmod(blob_path, 0o600)


def test_malformed_blob_schema_fails_closed_for_every_consumer_without_value_output(vault, run_cli, engine):
    """Schema validation runs before list/get/exec/migration can consume data."""
    malformed_value = "MALFORMED_schema_value_not_to_be_printed_12345"
    _write_unvalidated_blob(vault, engine, {
        "version": 1,
        "entries": {"test/secret": {"value": malformed_value, "meta": []}},
    })

    commands = (
        ("list",),
        ("get", "test/secret"),
        ("exec", "--ref", "test/secret", "--", sys.executable, "-c", "print('unreachable')"),
        ("migrate-refs",),
        ("recover", "get", "test/secret"),
    )
    for command in commands:
        r = run_cli(vault.root, "vault", *command, extra_env=vault.env)
        assert r.returncode != 0
        assert "schema is invalid" in (r.stdout + r.stderr).lower()
        assert malformed_value not in r.stdout + r.stderr


def test_mutation_lock_prevents_lost_updates(vault, engine):
    """A deterministic interleaving proves the second writer reads post-write state."""
    engine._vault_write_blob(vault.root, {"version": 1, "entries": {}})
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first_mutation(data):
        data["entries"]["one/secret"] = {"value": "ONE_value_not_printed", "meta": {}}
        first_entered.set()
        assert release_first.wait(timeout=5)

    def second_mutation(data):
        second_entered.set()
        data["entries"]["two/secret"] = {"value": "TWO_value_not_printed", "meta": {}}

    first = threading.Thread(target=lambda: engine._vault_mutate_blob(vault.root, first_mutation))
    second = threading.Thread(target=lambda: engine._vault_mutate_blob(vault.root, second_mutation))
    first.start()
    assert first_entered.wait(timeout=5)
    second.start()
    assert not second_entered.wait(timeout=0.25), "second writer entered before the first released the vault lock"
    release_first.set()
    first.join(timeout=10)
    second.join(timeout=10)
    assert not first.is_alive() and not second.is_alive()
    assert set(engine._vault_read_blob(vault.root)["entries"]) == {"one/secret", "two/secret"}


# ===========================================================================
# (2) vault exec — JIT injection with no plaintext leak from tessctl
# ===========================================================================

def _set(run_cli, vault, ref, value):
    r = run_cli(vault.root, "vault", "set", ref,
                input_text=value + "\n", extra_env=vault.env)
    assert r.returncode == 0, r.stderr


_CHILD_WRITE = (
    "import os,pathlib;"
    "pathlib.Path('child_out.txt').write_text(os.environ.get({var!r},'__MISSING__'));"
    "print('DONE')"
)


def test_exec_injects_secret_into_child_env(vault, run_cli):
    _set(run_cli, vault, "test/secret", SECRET)
    # default env var name: service/key -> SERVICE_KEY uppercase
    r = run_cli(vault.root, "vault", "exec", "--ref", "test/secret", "--",
                sys.executable, "-c", _CHILD_WRITE.format(var="TEST_SECRET"),
                extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert (vault.root / "child_out.txt").read_text() == SECRET


def test_exec_custom_env_var_name(vault, run_cli):
    _set(run_cli, vault, "test/secret", SECRET)
    r = run_cli(vault.root, "vault", "exec", "--ref", "test/secret",
                "--as", "MYTOKEN", "--",
                sys.executable, "-c", _CHILD_WRITE.format(var="MYTOKEN"),
                extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert (vault.root / "child_out.txt").read_text() == SECRET


def test_exec_no_plaintext_leak_in_tessctl_output(vault, run_cli):
    """The child receives the value (written to a file) but the vault layer
    itself emits NO plaintext to stdout/stderr."""
    _set(run_cli, vault, "test/secret", SECRET)
    r = run_cli(vault.root, "vault", "exec", "--ref", "test/secret", "--",
                sys.executable, "-c", _CHILD_WRITE.format(var="TEST_SECRET"),
                extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "DONE" in r.stdout                       # child ran
    assert (vault.root / "child_out.txt").read_text() == SECRET  # child got value
    assert SECRET not in r.stdout                   # tessctl leaked nothing
    assert SECRET not in r.stderr


def test_exec_exit_code_propagates(vault, run_cli):
    _set(run_cli, vault, "test/secret", SECRET)
    r = run_cli(vault.root, "vault", "exec", "--ref", "test/secret", "--",
                sys.executable, "-c", "import sys; sys.exit(7)",
                extra_env=vault.env)
    assert r.returncode == 7


def test_exec_missing_ref_errors_without_value(vault, run_cli):
    r = run_cli(vault.root, "vault", "exec", "--ref", "absent/ref", "--",
                sys.executable, "-c", "print('x')", extra_env=vault.env)
    assert r.returncode != 0
    out = r.stdout + r.stderr
    assert "not found" in out.lower()
    assert "absent/ref" in out  # echoes the ref name, not a value


# ===========================================================================
# (5) rotate re-encrypts; wrong identity cannot decrypt
# ===========================================================================

def test_rotate_reencrypts_new_value(vault, run_cli, engine):
    root = vault.root
    v1 = "OLD_value_aaaaaaaaaaaaaaaaaaaa"
    v2 = "NEW_value_bbbbbbbbbbbbbbbbbbbb"
    _set(run_cli, vault, "test/secret", v1)

    r = run_cli(root, "vault", "rotate", "test/secret",
                input_text=v2 + "\n", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "rotated" in r.stdout
    assert v2 not in r.stdout  # never echoes the new value

    # new value retrievable, old value gone from ciphertext
    r = run_cli(root, "vault", "get", "test/secret", "--reveal", extra_env=vault.env)
    assert r.stdout == v2

    raw = (root / ".claude" / "vault" / "vault.age").read_bytes()
    assert v1.encode() not in raw
    assert v2.encode() not in raw  # still encrypted

    data = engine._vault_read_blob(root)
    entry = data["entries"]["test/secret"]
    assert entry["value"] == v2
    assert "rotated_at" in entry["meta"]


def test_wrong_identity_cannot_decrypt(vault, run_cli, engine, monkeypatch):
    """The blob is bound to its recipient: a non-matching age identity cannot
    read it (the 'old identity can't decrypt, new can' property)."""
    _set(run_cli, vault, "test/secret", SECRET)

    other_priv, _ = engine._vault_generate_identity(vault.backend)
    monkeypatch.setenv("TESS_VAULT_IDENTITY", other_priv)
    with pytest.raises(SystemExit):
        engine._vault_read_blob(vault.root)

    # restore the correct identity → decrypts cleanly
    monkeypatch.setenv("TESS_VAULT_IDENTITY", vault.priv)
    data = engine._vault_read_blob(vault.root)
    assert data["entries"]["test/secret"]["value"] == SECRET


# ===========================================================================
# (6) fresh / empty vault ships with no secrets
# ===========================================================================

def test_empty_vault_lists_empty(vault, run_cli):
    # fixture created recipients + registry but never `set` anything → no blob
    r = run_cli(vault.root, "vault", "list", extra_env=vault.env)
    assert r.returncode == 0, r.stderr
    assert "empty" in r.stdout.lower()


def test_empty_vault_get_not_found(vault, run_cli):
    r = run_cli(vault.root, "vault", "get", "anything/here", extra_env=vault.env)
    assert r.returncode != 0
    assert "not found" in (r.stdout + r.stderr).lower()


def test_shipped_repo_tracks_no_vault_secrets():
    """The public repo must track only the value-free scaffold."""
    if not HAS_GIT:
        pytest.skip("git required")
    r = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", ".claude/vault/"],
        capture_output=True, text=True,
    )
    tracked = set(r.stdout.split())
    assert ".claude/vault/vault.age" not in tracked
    assert ".claude/vault/vault.recipients" not in tracked
    assert ".claude/vault/identity.age" not in tracked
    # only the scaffold is committed
    assert ".claude/vault/.gitkeep" in tracked
    assert ".claude/vault/vault.registry.json" in tracked


def test_shipped_registry_has_no_value_shaped_fields():
    reg_path = REPO_ROOT / ".claude" / "vault" / "vault.registry.json"
    assert reg_path.exists(), "registry scaffold must ship"
    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    # valid JSON, no value-shaped fields (the doctor --strict invariant)
    suspicious = re.findall(
        r'"(?:value|secret|password|api_key|token)"\s*:\s*"([^"]{8,})"',
        json.dumps(registry),
    )
    assert suspicious == []


# ===========================================================================
# (3) HARD-GUARD — vault paths refused by the manifest write gate
# ===========================================================================

@pytest.fixture
def gate_root(tmp_path):
    shutil.copy2(MANIFEST_SRC, tmp_path / "tess.manifest.json")
    return tmp_path


@pytest.fixture
def manifest():
    return json.loads(MANIFEST_SRC.read_text())


# Each must raise GateError with the vault-protected message — even
# agents/leah/notes.age, which sits inside the OWNED agents/** glob, proving
# owned_globs cannot override the hard guard.
VAULT_BLOCKED = [
    ".claude/vault/vault.age",
    ".claude/vault/identity.age",
    ".claude/vault/vault.recipients",
    ".claude/vault/sub/blob.age",
    "clients/ExampleClient/.vault/secret.txt",
    "agents/leah/notes.age",        # owned path, still blocked by **/*.age
]


@pytest.mark.parametrize("path", VAULT_BLOCKED)
def test_gate_blocks_vault_paths(engine, gate_root, manifest, path):
    with pytest.raises(engine.GateError) as ei:
        engine.check_manifest_write_gate(gate_root, manifest, path, op="test")
    assert "vault-protected" in str(ei.value)


# The only committable vault paths are exempt from the vault guard. They are
# still denied (not in owned_globs) but NOT by the vault hard-guard.
VAULT_EXEMPT = [
    ".claude/vault/.gitkeep",
    ".claude/vault/vault.registry.json",
]


@pytest.mark.parametrize("path", VAULT_EXEMPT)
def test_gate_exempts_committable_vault_scaffold(engine, gate_root, manifest, path):
    with pytest.raises(engine.GateError) as ei:
        engine.check_manifest_write_gate(gate_root, manifest, path, op="test")
    # exempt from the vault guard (caught later by the owned_globs ALLOWLIST)
    assert "vault-protected" not in str(ei.value)


def test_guarded_write_refuses_vault_blob(engine, gate_root, manifest):
    """The actual write path (used by render/restore/publish/capture/update)
    refuses vault material."""
    with pytest.raises(engine.GateError) as ei:
        engine.guarded_write(gate_root, ".claude/vault/vault.age", b"x",
                             op="render", manifest=manifest)
    assert "vault-protected" in str(ei.value)
    assert not (gate_root / ".claude" / "vault" / "vault.age").exists()


# ===========================================================================
# (4) scrub guards — gitignore + npmignore coverage
# ===========================================================================

GITIGNORED = [
    ".claude/vault/vault.age",
    ".claude/vault/vault.recipients",
    ".claude/vault/identity.age",
    "clients/ExampleClient/.vault/secret.txt",
    "foo.env.json",
]

GIT_COMMITTABLE = [
    ".claude/vault/.gitkeep",
    ".claude/vault/vault.registry.json",
]


@pytest.mark.skipif(not HAS_GIT, reason="git required")
@pytest.mark.parametrize("path", GITIGNORED)
def test_vault_paths_are_gitignored(path):
    r = subprocess.run(["git", "-C", str(REPO_ROOT), "check-ignore", "-q", path])
    assert r.returncode == 0, f"{path} should be gitignored"


@pytest.mark.skipif(not HAS_GIT, reason="git required")
@pytest.mark.parametrize("path", GIT_COMMITTABLE)
def test_committable_vault_paths_not_ignored(path):
    r = subprocess.run(["git", "-C", str(REPO_ROOT), "check-ignore", "-q", path])
    assert r.returncode == 1, f"{path} must remain committable"


def test_vault_patterns_in_npmignore():
    npmignore = (REPO_ROOT / ".npmignore").read_text(encoding="utf-8")
    for pat in [
        "*.env.json",
        ".claude/vault/vault.age",
        ".claude/vault/vault.recipients",
        ".claude/vault/identity.age",
        "**/vault.age",
        "**/identity.age",
        "clients/*/.vault/",
    ]:
        assert pat in npmignore, f"missing .npmignore pattern: {pat}"


# ===========================================================================
# doctor + scan — defense-in-depth audits
# ===========================================================================

def test_doctor_fails_without_gitignore(vault, run_cli):
    # synthetic project has no .gitignore → doctor reports a hard issue
    r = run_cli(vault.root, "vault", "doctor", extra_env=vault.env)
    assert r.returncode == 1
    assert "gitignore" in r.stdout.lower()


def test_doctor_strict_rejects_registry_values(vault, engine, monkeypatch, capsys, tmp_path):
    """doctor --strict flags a registry that smuggles a value-shaped field."""
    root = vault.root
    # make the non-strict checks pass so the strict failure is the signal
    shutil.copy2(REPO_ROOT / ".gitignore", root / ".gitignore")
    monkeypatch.setattr(engine, "_GLOBAL_IDENTITY_FILE", tmp_path / "no_identity")
    poisoned = {"services": {"x": {"token": "AAAAAAAAAAAAAAAA"}}}
    (root / ".claude" / "vault" / "vault.registry.json").write_text(
        json.dumps(poisoned), encoding="utf-8"
    )
    with pytest.raises(SystemExit) as ei:
        engine._vault_cmd_doctor(types.SimpleNamespace(strict=True), root)
    assert ei.value.code == 1
    out = capsys.readouterr().out.lower()
    assert "value-shaped" in out


def test_secret_patterns_match_known_secrets(engine):
    compiled = [re.compile(p, re.IGNORECASE) for p in engine.VAULT_SECRET_PATTERNS]
    samples = {
        # fragments joined at runtime so this source file carries no contiguous
        # secret-shaped literal (the repo's own vault pre-commit guard scans it)
        "github_pat": "ghp_" + "a" * 36,
        "aws": "AKIA" + "ABCDEFGHIJKLMNOP",
        "stripe": "sk_live_" + "a" * 24,
        "age_priv": "AGE-SECRET-KEY-" + "A" * 55,
        "pem": "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
        "assignment": "api_key = '" + ("z" * 26) + "'",
    }
    for name, text in samples.items():
        assert any(p.search(text) for p in compiled), f"missed {name}"
    assert not any(
        p.search("the quick brown fox jumps over the lazy dog 12345")
        for p in compiled
    )


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_scan_flags_tracked_secret(tmp_path, engine, run_cli):
    scan = Project(tmp_path / "scanrepo", engine)
    root = scan.root
    for a in (("init", "-q"), ("config", "user.email", "t@t.test"),
              ("config", "user.name", "t")):
        subprocess.run(["git", "-C", str(root), *a], capture_output=True)
    # contiguous in the written file (so scan detects it), split in source
    (root / "leak.txt").write_text("aws key: " + "AKIA" + "ABCDEFGHIJKLMNOP" + "\n")
    subprocess.run(["git", "-C", str(root), "add", "leak.txt"], capture_output=True)
    r = run_cli(root, "vault", "scan")
    assert r.returncode == 1
    assert "leak.txt" in r.stdout


@pytest.mark.skipif(not HAS_GIT, reason="git required")
def test_scan_clean_tree(tmp_path, engine, run_cli):
    scan = Project(tmp_path / "scanclean", engine)
    root = scan.root
    for a in (("init", "-q"), ("config", "user.email", "t@t.test"),
              ("config", "user.name", "t")):
        subprocess.run(["git", "-C", str(root), *a], capture_output=True)
    (root / "clean.txt").write_text("nothing sensitive here, just prose.\n")
    subprocess.run(["git", "-C", str(root), "add", "clean.txt"], capture_output=True)
    r = run_cli(root, "vault", "scan")
    assert r.returncode == 0
    assert "clean" in r.stdout
