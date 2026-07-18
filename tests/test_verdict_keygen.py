"""
`tessctl verdict keygen` — turnkey Phase 2b onboarding (Goal #2: "make the
flagship signed ship-gate usable OUT-OF-THE-BOX"). Closes the adoption gap
`core/policy/policy.yaml` and `conductor/verdict-signing.md` both disclose:
`verifier_keys` ships empty on purpose, but a fresh adopter had no
mechanical path from "I want a real verifier" to a registered signing key
short of hand-running `gpg --full-gen-key` / `gpg --export` and hand-editing
TWO copies of `policy.yaml` without tripping `doctor`/`verify`/`lock --check`.

Coverage:
  * `_policy_yaml_upsert_verifier_key` (the comment-preserving text patcher)
    — empty-to-one-entry, add-a-second-entry, replace-an-existing-entry
    (idempotency/`--force` semantics live in the CLI layer, not here), and
    the `ValueError` when no `verifier_keys:` key exists at all. Exercised
    against the REAL shipped `core/policy/policy.yaml` so the comment-
    preservation proof is real, not a synthetic stand-in — but normalized
    back to a clean, empty `verifier_keys: {}` baseline first (see
    `_policy_text_with_empty_verifier_keys` below), so this suite never
    depends on which real verifiers (e.g. Cyra) happen to be registered
    live in this repo at test time.
  * `tessctl verdict keygen` CLI: generates + registers + re-pins;
    idempotent refusal without `--force`; `--force` rotates; unknown
    verifier name rejected; missing `gpg` on PATH is a clear, fail-closed
    error; a core/live policy.yaml drift is refused BEFORE any write; a
    JSON policy instance is refused (comment-preserving patch is YAML-only);
    a missing policy instance is refused.
  * Integration: a keygen-generated key actually signs a verdict that
    clears `tessctl gate ci`; a DIFFERENT (non-keygen) key claiming to be
    the keygen-registered verifier still BLOCKS; a verdict tampered after
    signing with a keygen-generated key still BLOCKS.
  * `tessctl doctor` / `verify` / `lock --check` are asserted clean after
    every successful keygen call — the VERIFY requirement in the dispatch
    brief.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"
POLICY_SRC = REPO_ROOT / "core" / "policy" / "policy.yaml"

HAS_GIT = shutil.which("git") is not None
HAS_GPG = shutil.which("gpg") is not None
pytestmark = pytest.mark.skipif(not (HAS_GIT and HAS_GPG), reason="git + gpg required")


def _policy_text_with_empty_verifier_keys(text: str) -> str:
    """Reset `policy.verifier_keys` in `text` back to the clean, empty
    inline form (`verifier_keys: {}`), leaving every other line — including
    every comment, rule, and hard_floor_rule — byte-for-byte untouched.

    These fixtures deliberately still read the REAL shipped `core/policy/
    policy.yaml` (so the comment-preservation proof below is real, not a
    synthetic stand-in) but must NOT depend on which verifiers happen to
    already be registered live in THIS repo at test time — the whole point
    of Phase 1 was to register Cyra's real key, and this suite would break
    every time a new real verifier is onboarded if it asserted anything
    about the live `verifier_keys` map's current contents. Normalizing back
    to the shipped-clean baseline here decouples "does the upsert/keygen
    machinery behave correctly" from "what is presently registered in prod."

    Deliberately duplicates (rather than imports) the engine's own
    `verifier_keys:` block-detection logic, so a bug in this test helper can
    never mask a real regression in the function under test.
    """
    lines = text.splitlines(keepends=True)

    def _indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    vk_idx = None
    vk_indent = None
    for i, line in enumerate(lines):
        if line.lstrip(" ").startswith("#"):
            continue  # skip commented-out example blocks (e.g. the shipped walkthrough)
        if line.strip() in ("verifier_keys: {}", "verifier_keys:"):
            vk_idx = i
            vk_indent = _indent_of(line)
            break
    assert vk_idx is not None, "no `verifier_keys:` key found in core/policy/policy.yaml"

    if lines[vk_idx].strip() == "verifier_keys: {}":
        return text  # already clean — nothing to reset

    end_idx = vk_idx + 1
    while end_idx < len(lines):
        line = lines[end_idx]
        if line.strip() == "":
            end_idx += 1
            continue
        if _indent_of(line) <= vk_indent:
            break
        end_idx += 1

    lines[vk_idx:end_idx] = [f"{' ' * vk_indent}verifier_keys: {{}}\n"]
    return "".join(lines)


@pytest.fixture
def make_gnupg_home():
    """Factory for short-prefixed GNUPGHOME dirs under /tmp (NOT pytest's
    deep tmp_path — the gpg-agent UNIX socket path has a ~104-char limit
    and pytest's nested tmp dirs blow past it; see conftest.py's `gpg_key`
    fixture, which documents and works around the exact same constraint).
    Each call returns a fresh dir; all of them are torn down (agent killed,
    directory removed) at the end of the test."""
    homes: list[Path] = []

    def _make() -> Path:
        home = Path(tempfile.mkdtemp(prefix="tessgpgkg", dir="/tmp"))
        os.chmod(home, 0o700)
        homes.append(home)
        return home

    yield _make

    for home in homes:
        subprocess.run(
            ["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"],
            capture_output=True, env={**os.environ, "GNUPGHOME": str(home)},
        )
        shutil.rmtree(str(home), ignore_errors=True)


# ---------------------------------------------------------------------------
# Unit tests: `_policy_yaml_upsert_verifier_key` (comment-preserving patcher)
# ---------------------------------------------------------------------------


def test_upsert_converts_empty_inline_form_to_one_entry(engine):
    text = _policy_text_with_empty_verifier_keys(POLICY_SRC.read_text(encoding="utf-8"))
    new_text, existed = engine._policy_yaml_upsert_verifier_key(
        text, "Reid", "AAAA0000AAAA0000AAAA0000AAAA0000AAAA0000", ".tess/keys/verifiers/reid.asc",
    )
    assert existed is False
    parsed = yaml.safe_load(new_text)
    assert parsed["policy"]["verifier_keys"] == {
        "Reid": {
            "fingerprint": "AAAA0000AAAA0000AAAA0000AAAA0000AAAA0000",
            "public_key_file": ".tess/keys/verifiers/reid.asc",
        }
    }
    # Comment preservation: every commented line in the original survives,
    # untouched, at the same count (the real proof this isn't a plain
    # yaml.safe_load + yaml.safe_dump round-trip, which would drop them all).
    orig_comments = [l for l in text.splitlines() if l.lstrip().startswith("#")]
    new_comments = [l for l in new_text.splitlines() if l.lstrip().startswith("#")]
    assert new_comments == orig_comments
    # The rest of the policy (rules, hard_floor_rules) is untouched.
    orig_parsed = yaml.safe_load(text)
    assert parsed["policy"]["rules"] == orig_parsed["policy"]["rules"]
    assert parsed["policy"]["hard_floor_rules"] == orig_parsed["policy"]["hard_floor_rules"]


def test_upsert_adds_a_second_entry_after_the_first(engine):
    text = _policy_text_with_empty_verifier_keys(POLICY_SRC.read_text(encoding="utf-8"))
    text, _ = engine._policy_yaml_upsert_verifier_key(
        text, "Reid", "AAAA0000AAAA0000AAAA0000AAAA0000AAAA0000", ".tess/keys/verifiers/reid.asc",
    )
    new_text, existed = engine._policy_yaml_upsert_verifier_key(
        text, "Cyra", "BBBB1111BBBB1111BBBB1111BBBB1111BBBB1111", ".tess/keys/verifiers/cyra.asc",
    )
    assert existed is False
    parsed = yaml.safe_load(new_text)
    keys = parsed["policy"]["verifier_keys"]
    assert set(keys) == {"Reid", "Cyra"}
    assert keys["Reid"]["fingerprint"] == "AAAA0000AAAA0000AAAA0000AAAA0000AAAA0000"
    assert keys["Cyra"]["fingerprint"] == "BBBB1111BBBB1111BBBB1111BBBB1111BBBB1111"


def test_upsert_replaces_an_existing_entry_in_place(engine):
    text = _policy_text_with_empty_verifier_keys(POLICY_SRC.read_text(encoding="utf-8"))
    text, _ = engine._policy_yaml_upsert_verifier_key(
        text, "Reid", "AAAA0000AAAA0000AAAA0000AAAA0000AAAA0000", ".tess/keys/verifiers/reid.asc",
    )
    text, _ = engine._policy_yaml_upsert_verifier_key(
        text, "Cyra", "BBBB1111BBBB1111BBBB1111BBBB1111BBBB1111", ".tess/keys/verifiers/cyra.asc",
    )
    new_text, existed = engine._policy_yaml_upsert_verifier_key(
        text, "Reid", "CCCC2222CCCC2222CCCC2222CCCC2222CCCC2222", ".tess/keys/verifiers/reid.asc",
    )
    assert existed is True
    parsed = yaml.safe_load(new_text)
    keys = parsed["policy"]["verifier_keys"]
    assert keys["Reid"]["fingerprint"] == "CCCC2222CCCC2222CCCC2222CCCC2222CCCC2222"
    # Cyra's entry — registered in a separate call — is untouched.
    assert keys["Cyra"]["fingerprint"] == "BBBB1111BBBB1111BBBB1111BBBB1111BBBB1111"
    assert len(parsed["policy"]["hard_floor_rules"]) == 4


def test_upsert_raises_when_no_verifier_keys_key_present(engine):
    text = "policy:\n  version: 1\n  rules: []\n  hard_floor_rules: []\n"
    with pytest.raises(ValueError, match="no `verifier_keys:`"):
        engine._policy_yaml_upsert_verifier_key(text, "Reid", "A" * 40, "x.asc")


# ---------------------------------------------------------------------------
# CLI: `tessctl verdict keygen` — project-fixture-backed (lock-tracked so
# doctor/verify/lock --check are meaningful)
# ---------------------------------------------------------------------------


def _seed_keygen_project(project):
    """A project with core/policy/policy.yaml (the REAL shipped content —
    proving the comment-preservation guarantee end to end through the CLI —
    with `verifier_keys` normalized back to its shipped-clean `{}` baseline
    via `_policy_text_with_empty_verifier_keys`, so these tests model a
    fresh adopter's project rather than accidentally inheriting whichever
    real verifiers happen to be registered live in THIS repo) lock-tracked,
    plus the real contract schemas (needed by keygen's own schema/lint
    sanity check before it writes anything)."""
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    project.add(
        "core/policy/policy.yaml",
        content=_policy_text_with_empty_verifier_keys(POLICY_SRC.read_text(encoding="utf-8")),
        tier="security",
        core_key=".tess/core/policy/policy.yaml",
    )
    project.write()
    return root


@pytest.fixture
def keygen_project(project):
    return _seed_keygen_project(project)


def _gen_raw_secret_key(gnupg_home: Path, email: str, name_real: str) -> str:
    """Generate a throwaway secret key DIRECTLY with gpg (bypassing tessctl
    entirely) in `gnupg_home`, using `email` as its Name-Email. Used to seed
    a keyring with a PRE-EXISTING key that shares keygen's own
    `<name>@verifier.tessctl.local` uid_email convention — either an
    attacker-planted key (collision test) or a to-be-retired key (rotation
    test) — so a test can prove keygen resolves the fingerprint of the key
    IT just generated, never one it merely shares an email with. Returns the
    new key's 40-hex fingerprint, uppercase."""
    params = (
        "%no-protection\n"
        "Key-Type: RSA\n"
        "Key-Length: 2048\n"
        "Key-Usage: sign\n"
        f"Name-Real: {name_real}\n"
        f"Name-Email: {email}\n"
        "Expire-Date: 0\n"
        "%commit\n"
    )
    env = {**os.environ, "GNUPGHOME": str(gnupg_home)}
    r = subprocess.run(
        ["gpg", "--batch", "--gen-key"],
        input=params.encode("utf-8"), capture_output=True, env=env,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", errors="replace")
    lk = subprocess.run(
        ["gpg", "--list-secret-keys", "--with-colons", email],
        capture_output=True, env=env,
    )
    fpr = ""
    for line in lk.stdout.decode("utf-8", errors="replace").splitlines():
        if line.startswith("fpr:"):
            fpr = line.split(":")[9]
            break
    assert fpr, f"could not extract fingerprint for {email}"
    return fpr.upper()


def _secret_key_fprs_for_email(gnupg_home: Path, email: str) -> list[str]:
    """All secret-key fingerprints in `gnupg_home` matching `email`, in the
    order gpg lists them (creation order) — used to independently confirm
    which key is oldest/newest in a shared keyring, so a test's assumption
    about ordering isn't just taken on faith."""
    env = {**os.environ, "GNUPGHOME": str(gnupg_home)}
    lk = subprocess.run(
        ["gpg", "--list-secret-keys", "--with-colons", email],
        capture_output=True, env=env,
    )
    return [
        line.split(":")[9]
        for line in lk.stdout.decode("utf-8", errors="replace").splitlines()
        if line.startswith("fpr:")
    ]


def _export_armored(gnupg_home: Path, fingerprint: str) -> str:
    env = {**os.environ, "GNUPGHOME": str(gnupg_home)}
    r = subprocess.run(
        ["gpg", "--homedir", str(gnupg_home), "--export", "--armor", fingerprint],
        capture_output=True, env=env,
    )
    return r.stdout.decode("utf-8")


def test_keygen_ignores_preexisting_key_sharing_uid_email_in_same_keyring(
    keygen_project, run_cli, make_gnupg_home,
):
    """Regression test for the HIGH finding (Fable, reproduced end-to-end):
    keygen resolved WHICH fingerprint to register by re-querying
    `gpg --list-secret-keys --with-colons <uid_email>` and taking the FIRST
    `fpr:` line. `uid_email` (`<name>@verifier.tessctl.local`) is fixed and
    non-unique, so a keyring that already holds ANY other key sharing that
    email — e.g. an attacker-planted key — caused keygen to register +
    export THAT pre-existing key instead of the one it had just generated.

    Deliberately pre-seeds the SAME GNUPGHOME keygen will use (not a
    separate one — the pre-existing test suite's use of two separate
    GNUPGHOMEs per keygen call was the exact blind spot that let this bug
    ship undetected) with an attacker key using Reid's uid_email BEFORE
    calling keygen. gpg lists secret keys in creation order, so a naive
    by-email re-query would return the attacker's (older) key first."""
    gnupg_home = make_gnupg_home()
    attacker_fpr = _gen_raw_secret_key(
        gnupg_home, "reid@verifier.tessctl.local", "Attacker-planted Reid",
    )

    r = run_cli(keygen_project, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(gnupg_home))
    assert r.returncode == 0, r.stdout + r.stderr

    live = yaml.safe_load((keygen_project / "core" / "policy" / "policy.yaml").read_text())
    registered_fpr = live["policy"]["verifier_keys"]["Reid"]["fingerprint"]

    # The registered fingerprint must be the key keygen just generated —
    # NEVER the attacker's pre-existing one.
    assert registered_fpr != attacker_fpr

    fprs = _secret_key_fprs_for_email(gnupg_home, "reid@verifier.tessctl.local")
    assert len(fprs) == 2, fprs
    assert fprs[0] == attacker_fpr  # confirms the attacker's key IS the older/first one
    assert fprs[1] == registered_fpr  # keygen registered the newer/second (its own) key

    # The exported public key on disk must be the newly-generated key's
    # export, not the attacker's.
    key_file = keygen_project / ".tess" / "keys" / "verifiers" / "reid.asc"
    exported_armored = key_file.read_text(encoding="utf-8")
    assert exported_armored == _export_armored(gnupg_home, registered_fpr)
    assert exported_armored != _export_armored(gnupg_home, attacker_fpr)

    d = run_cli(keygen_project, "doctor")
    assert d.returncode == 0, d.stdout + d.stderr
    v = run_cli(keygen_project, "verify")
    assert v.returncode == 0, v.stdout + v.stderr


def test_keygen_force_rotation_in_shared_keyring_registers_the_new_key(
    keygen_project, run_cli, make_gnupg_home,
):
    """Regression test for the HIGH finding's rotation-specific corollary:
    `gpg --list-secret-keys <uid_email>` returns BOTH keys once a keyring
    has an original + a `--force` rotation, oldest first — a by-email
    re-query therefore picked the OLDER key, meaning `--force` re-registered
    the very key the operator was trying to retire (compromise persists).

    Runs keygen TWICE against ONE shared GNUPGHOME (unlike
    `test_keygen_force_rotates_key_and_stays_clean` above, which uses two
    SEPARATE GNUPGHOMEs per call and so never exercises the keyring-
    collision path a real rotation actually hits) and asserts the second
    call registers the fingerprint of the key IT just generated — the
    newest one — never the first/retiring one."""
    gnupg_home = make_gnupg_home()

    r1 = run_cli(keygen_project, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(gnupg_home))
    assert r1.returncode == 0, r1.stdout + r1.stderr
    live1 = yaml.safe_load((keygen_project / "core" / "policy" / "policy.yaml").read_text())
    fp1 = live1["policy"]["verifier_keys"]["Reid"]["fingerprint"]

    r2 = run_cli(
        keygen_project, "verdict", "keygen", "--verifier", "Reid",
        "--gnupg-home", str(gnupg_home), "--force",
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr
    live2 = yaml.safe_load((keygen_project / "core" / "policy" / "policy.yaml").read_text())
    fp2 = live2["policy"]["verifier_keys"]["Reid"]["fingerprint"]

    # Rotation must land on the NEW key — never re-select the retiring one.
    assert fp2 != fp1

    fprs = _secret_key_fprs_for_email(gnupg_home, "reid@verifier.tessctl.local")
    assert len(fprs) == 2, fprs
    assert fprs[0] == fp1  # the original/retiring key — oldest, listed first by gpg
    assert fprs[1] == fp2  # the rotation's new key — what must be registered

    assert (keygen_project / "core" / "policy" / "policy.yaml").read_bytes() == \
        (keygen_project / ".tess" / "core" / "policy" / "policy.yaml").read_bytes()
    d = run_cli(keygen_project, "doctor")
    assert d.returncode == 0, d.stdout + d.stderr
    lc = run_cli(keygen_project, "lock", "--check")
    assert lc.returncode == 0, lc.stdout + lc.stderr

    # The public key exported to disk must be the NEW key's, not the old one's.
    key_file = keygen_project / ".tess" / "keys" / "verifiers" / "reid.asc"
    exported_armored = key_file.read_text(encoding="utf-8")
    assert exported_armored == _export_armored(gnupg_home, fp2)
    assert exported_armored != _export_armored(gnupg_home, fp1)


def test_keygen_generates_registers_and_repins_cleanly(keygen_project, run_cli, make_gnupg_home):
    gnupg_home = make_gnupg_home()
    r = run_cli(keygen_project, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(gnupg_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "generated a new sign-only GPG identity for verifier 'Reid'" in r.stdout

    key_file = keygen_project / ".tess" / "keys" / "verifiers" / "reid.asc"
    assert key_file.exists()
    assert "BEGIN PGP PUBLIC KEY BLOCK" in key_file.read_text(encoding="utf-8")

    live = yaml.safe_load((keygen_project / "core" / "policy" / "policy.yaml").read_text())
    core = yaml.safe_load((keygen_project / ".tess" / "core" / "policy" / "policy.yaml").read_text())
    assert live["policy"]["verifier_keys"]["Reid"]["public_key_file"] == ".tess/keys/verifiers/reid.asc"
    fingerprint = live["policy"]["verifier_keys"]["Reid"]["fingerprint"]
    assert len(fingerprint) == 40
    assert core["policy"]["verifier_keys"]["Reid"]["fingerprint"] == fingerprint
    # Live and core copies stay byte-identical (the pristine-mirror invariant).
    assert (keygen_project / "core" / "policy" / "policy.yaml").read_bytes() == \
        (keygen_project / ".tess" / "core" / "policy" / "policy.yaml").read_bytes()

    # VERIFY requirement: doctor / verify / lock --check all clean afterward.
    d = run_cli(keygen_project, "doctor")
    assert d.returncode == 0, d.stdout + d.stderr
    assert "doctor: OK" in d.stdout
    v = run_cli(keygen_project, "verify")
    assert v.returncode == 0, v.stdout + v.stderr
    assert "verify: OK" in v.stdout
    lc = run_cli(keygen_project, "lock", "--check")
    assert lc.returncode == 0, lc.stdout + lc.stderr
    assert "OK" in lc.stdout


def test_keygen_refuses_to_clobber_existing_key_without_force(keygen_project, run_cli, make_gnupg_home):
    gnupg_home = make_gnupg_home()
    r1 = run_cli(keygen_project, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(gnupg_home))
    assert r1.returncode == 0, r1.stdout + r1.stderr

    r2 = run_cli(keygen_project, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(gnupg_home))
    assert r2.returncode != 0
    assert "refusing to clobber" in (r2.stdout + r2.stderr)
    assert "--force" in (r2.stdout + r2.stderr)


def test_keygen_force_rotates_key_and_stays_clean(keygen_project, run_cli, make_gnupg_home):
    home1 = make_gnupg_home()
    home2 = make_gnupg_home()
    r1 = run_cli(keygen_project, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(home1))
    assert r1.returncode == 0, r1.stdout + r1.stderr
    live1 = yaml.safe_load((keygen_project / "core" / "policy" / "policy.yaml").read_text())
    fp1 = live1["policy"]["verifier_keys"]["Reid"]["fingerprint"]

    r2 = run_cli(keygen_project, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(home2), "--force")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    live2 = yaml.safe_load((keygen_project / "core" / "policy" / "policy.yaml").read_text())
    fp2 = live2["policy"]["verifier_keys"]["Reid"]["fingerprint"]

    assert fp1 != fp2
    assert (keygen_project / "core" / "policy" / "policy.yaml").read_bytes() == \
        (keygen_project / ".tess" / "core" / "policy" / "policy.yaml").read_bytes()

    d = run_cli(keygen_project, "doctor")
    assert d.returncode == 0, d.stdout + d.stderr
    lc = run_cli(keygen_project, "lock", "--check")
    assert lc.returncode == 0, lc.stdout + lc.stderr


def test_keygen_rejects_unknown_verifier_name(keygen_project, run_cli, make_gnupg_home):
    r = run_cli(
        keygen_project, "verdict", "keygen", "--verifier", "NotARealVerifier",
        "--gnupg-home", str(make_gnupg_home()),
    )
    assert r.returncode != 0
    assert "not one of the six named verifiers" in (r.stdout + r.stderr)
    # No key material should have been generated for an invalid name.
    assert not (keygen_project / ".tess" / "keys" / "verifiers" / "notarealverifier.asc").exists()


def test_keygen_requires_gpg_on_path(keygen_project, run_cli, tmp_path):
    # A PATH with no gpg on it — keygen must fail closed with a clear message
    # BEFORE touching anything, not a raw FileNotFoundError traceback.
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    r = run_cli(
        keygen_project, "verdict", "keygen", "--verifier", "Reid",
        extra_env={"PATH": str(empty_bin)},
    )
    assert r.returncode != 0
    assert "gpg" in (r.stdout + r.stderr).lower()
    assert "not found on PATH" in (r.stdout + r.stderr)
    live = yaml.safe_load((keygen_project / "core" / "policy" / "policy.yaml").read_text())
    assert not (live["policy"].get("verifier_keys") or {})


def test_keygen_refuses_on_core_live_drift_before_writing_anything(keygen_project, run_cli, make_gnupg_home):
    # Deliberately desync the live copy from the core mirror — keygen must
    # refuse rather than silently pick one side and patch it.
    live_path = keygen_project / "core" / "policy" / "policy.yaml"
    live_path.write_text(live_path.read_text(encoding="utf-8") + "\n# drifted\n", encoding="utf-8")

    r = run_cli(keygen_project, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(make_gnupg_home()))
    assert r.returncode != 0
    assert "NOT byte-identical" in (r.stdout + r.stderr)
    assert not (keygen_project / ".tess" / "keys" / "verifiers" / "reid.asc").exists()


def test_keygen_refuses_json_policy_instance(project, run_cli, make_gnupg_home):
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    (root / "core" / "policy").mkdir(parents=True, exist_ok=True)
    policy = {
        "policy": {
            "version": 1,
            "rules": [],
            "hard_floor_rules": [],
            "verifier_keys": {},
        }
    }
    (root / "core" / "policy" / "policy.json").write_text(json.dumps(policy), encoding="utf-8")

    r = run_cli(root, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(make_gnupg_home()))
    assert r.returncode != 0
    assert "is JSON" in (r.stdout + r.stderr)


def test_keygen_refuses_when_no_policy_instance_found(project, run_cli, make_gnupg_home):
    project.write()
    r = run_cli(project.root, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(make_gnupg_home()))
    assert r.returncode != 0
    assert "no policy instance found" in (r.stdout + r.stderr)


# ---------------------------------------------------------------------------
# Integration: a keygen-generated key actually functions as a real verifier
# key against the real gate — clears when properly signed, still blocks a
# wrong-key signature or a post-signing tamper.
# ---------------------------------------------------------------------------


def _init_repo(root):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@tess.test",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@tess.test"}
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, env=env)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@tess.test"], check=True, env=env)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True, env=env)
    subprocess.run(["git", "-C", str(root), "config", "commit.gpgsign", "false"], check=True, env=env)


def _git(root, *args, check=True):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@tess.test",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@tess.test"}
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}\n{r.stdout}")
    return r


def _base_verdict(covers_paths, artifact_hashes, verifier="Reid"):
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


@pytest.fixture
def keygen_git_repo(project, run_cli, make_gnupg_home):
    """A real git repo (with the engine + a real, lock-tracked policy.yaml —
    via the `project` fixture, same as `keygen_project` above) whose only
    require_verdict rule (prod-src, allowing Reid) is satisfied by a key
    `tessctl verdict keygen` generates — not a pre-seeded test fixture key.
    Proves keygen's OUTPUT is a real, working verifier identity, not just
    that the command exits 0."""
    root = project.root
    shutil.copytree(CONTRACTS_SRC, root / "core" / "contracts")
    policy = {
        "policy": {
            "version": 1,
            "rules": [{
                "id": "prod-src",
                "description": "test-only prod rule",
                "globs": ["src/prod/**"],
                "classification": ["prod_touching"],
                "require_verdict": True,
                "allowed_verifiers": ["Reid"],
            }],
            "hard_floor_rules": [],
            "verifier_keys": {},
        }
    }
    project.add(
        "core/policy/policy.yaml",
        content=yaml.safe_dump(policy),
        tier="security",
        core_key=".tess/core/policy/policy.yaml",
    )
    project.write()
    _init_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")

    gnupg_home = make_gnupg_home()
    r = run_cli(root, "verdict", "keygen", "--verifier", "Reid", "--gnupg-home", str(gnupg_home))
    assert r.returncode == 0, r.stdout + r.stderr
    fingerprint = yaml.safe_load(
        (root / "core" / "policy" / "policy.yaml").read_text()
    )["policy"]["verifier_keys"]["Reid"]["fingerprint"]

    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "register Reid's keygen-generated key")
    return root, gnupg_home, fingerprint


def test_keygen_then_sign_clears_gate_ci(keygen_git_repo, run_cli):
    root, gnupg_home, fingerprint = keygen_git_repo
    base = _git(root, "rev-parse", "HEAD").stdout.strip()

    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _git(root, "hash-object", "src/prod/app.py").stdout.strip()
    verdict_path = _write_verdict(
        root, "missions/m1/verdicts/prod-src.verdict.md",
        _base_verdict(["src/prod/**"], {"src/prod/app.py": blob}),
    )

    r_sign = run_cli(
        root, "verdict", "sign", str(verdict_path),
        "--verifier", "Reid", "--key-id", fingerprint, "--gnupg-home", str(gnupg_home),
    )
    assert r_sign.returncode == 0, r_sign.stdout + r_sign.stderr

    r_verify = run_cli(root, "verdict", "verify", str(verdict_path), "--json")
    assert r_verify.returncode == 0, r_verify.stdout + r_verify.stderr
    assert json.loads(r_verify.stdout)["valid"] is True

    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "prod change + signed verdict")
    head = _git(root, "rev-parse", "HEAD").stdout.strip()

    r_gate = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r_gate.returncode == 0, r_gate.stdout + r_gate.stderr
    payload = json.loads(r_gate.stdout)
    assert payload["blocked"] is False
    assert payload["reasons"] == []


def test_wrong_key_after_keygen_still_blocks(keygen_git_repo, run_cli, verifier_gpg_keys):
    """A signature that is genuinely, validly made — just with a DIFFERENT
    key than the one `keygen` registered for Reid — must not clear."""
    root, gnupg_home, fingerprint = keygen_git_repo
    base = _git(root, "rev-parse", "HEAD").stdout.strip()

    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _git(root, "hash-object", "src/prod/app.py").stdout.strip()
    verdict = _base_verdict(["src/prod/**"], {"src/prod/app.py": blob}, verifier="Reid")
    _write_verdict(root, "missions/m1/verdicts/prod-src.verdict.md", verdict)

    verdict_path = root / "missions" / "m1" / "verdicts" / "prod-src.verdict.md"
    r_sign = run_cli(
        root, "verdict", "sign", str(verdict_path),
        "--verifier", "Reid", "--key-id", verifier_gpg_keys["Lysandra"].fpr,
        "--gnupg-home", str(verifier_gpg_keys["Lysandra"].home),
    )
    assert r_sign.returncode == 0, r_sign.stdout + r_sign.stderr

    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "prod change + wrong-key signature")
    head = _git(root, "rev-parse", "HEAD").stdout.strip()

    r_gate = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r_gate.returncode == 1, r_gate.stdout + r_gate.stderr
    payload = json.loads(r_gate.stdout)
    assert payload["blocked"] is True
    assert any(
        "src/prod/app.py" in reason and ("does NOT match" in reason or "verification failed" in reason)
        for reason in payload["reasons"]
    )


def test_tampered_verdict_after_keygen_still_blocks(keygen_git_repo, run_cli, engine):
    root, gnupg_home, fingerprint = keygen_git_repo
    base = _git(root, "rev-parse", "HEAD").stdout.strip()

    (root / "src" / "prod").mkdir(parents=True)
    (root / "src" / "prod" / "app.py").write_text("print('prod')\n")
    blob = _git(root, "hash-object", "src/prod/app.py").stdout.strip()
    verdict_path = _write_verdict(
        root, "missions/m1/verdicts/prod-src.verdict.md",
        _base_verdict(["src/prod/**"], {"src/prod/app.py": blob}),
    )
    r_sign = run_cli(
        root, "verdict", "sign", str(verdict_path),
        "--verifier", "Reid", "--key-id", fingerprint, "--gnupg-home", str(gnupg_home),
    )
    assert r_sign.returncode == 0, r_sign.stdout + r_sign.stderr

    # Tamper AFTER signing: change the summary line (any field would do) —
    # without re-signing, so `signed_content_sha256` no longer matches. Uses
    # the engine's own load/write helpers (the same ones `verdict sign`
    # itself uses) rather than hand-parsing the front-matter, since a naive
    # text split can be fooled by yaml.safe_dump's own line-wrapping.
    instance = engine.load_contract_instance(verdict_path)
    instance["summary_line"] = instance["summary_line"] + " TAMPERED."
    engine.write_contract_instance_preserving_format(verdict_path, instance)

    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "prod change + tampered-after-signing verdict")
    head = _git(root, "rev-parse", "HEAD").stdout.strip()

    r_gate = run_cli(root, "gate", "ci", "--base", base, "--head", head, "--json")
    assert r_gate.returncode == 1, r_gate.stdout + r_gate.stderr
    payload = json.loads(r_gate.stdout)
    assert payload["blocked"] is True
    assert any("src/prod/app.py" in reason and "tampered" in reason for reason in payload["reasons"])
