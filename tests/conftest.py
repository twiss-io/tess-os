"""
Shared fixtures + helpers for the tessctl merge-engine test suite.

The engine is a single-file Python script with no .py extension
(/tmp/tess-os-build/.tess/bin/tessctl). We load it as an importable module via
SourceFileLoader so tests can call its functions directly. main() only runs
under __main__, so loading never executes the CLI.

Two project-construction strategies:
  * `project` fixture → a small synthetic Tess OS root with full control over
    lock entries (status / tier / base_sha / live_path) and staging content.
    Used for unit-level coverage of the merge engine, doctor, gate, etc.
  * real upstream git repos signed with a generated GPG key, used by the FETCH
    and self-update suites for genuine end-to-end signature verification.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Locate the engine + the real manifest (authoritative owned_globs/never_touch)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_SRC = REPO_ROOT / ".tess" / "bin" / "tessctl"
MANIFEST_SRC = REPO_ROOT / "tess.manifest.json"

HAS_GPG = shutil.which("gpg") is not None
HAS_GIT = shutil.which("git") is not None


def _load_engine():
    loader = importlib.machinery.SourceFileLoader("tessctl_engine", str(ENGINE_SRC))
    spec = importlib.util.spec_from_loader("tessctl_engine", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def engine():
    """The imported tessctl module (session-scoped — loaded once)."""
    return _load_engine()


# ---------------------------------------------------------------------------
# Synthetic project builder
# ---------------------------------------------------------------------------


class Project:
    """A throwaway Tess OS root the engine can operate on.

    add()      registers a core file + lock entry, and (by default) renders the
               matching live file so the tree starts pristine.
    stage()    writes a staging/<core_key> file (the 'incoming' upstream version).
    write()    flushes tess.manifest.json + .tess/tess.lock to disk and returns
               the loaded lock dict.
    """

    def __init__(self, root: Path, mod):
        self.root = root
        self.mod = mod
        self.files: dict[str, dict] = {}
        self.framework: dict = {
            "track": "v2",
            "version": "2.0.0",
            "channel": "stable",
            "upstream": "",
            "upstream_ref": "v2.0.0",
            "upstream_commit": None,
            "upstream_digest": None,
            "trusted_key_fingerprint": "",
            "last_updated": "2026-06-27T00:00:00.000000Z",
        }
        # Scaffold the .tess working dirs the engine expects.
        (root / ".tess" / "bin").mkdir(parents=True, exist_ok=True)
        (root / ".tess" / "core").mkdir(parents=True, exist_ok=True)
        (root / ".tess" / "staging").mkdir(parents=True, exist_ok=True)
        (root / ".tess" / "snapshots").mkdir(parents=True, exist_ok=True)
        # Copy the engine in so subprocess CLI runs work too.
        dst_engine = root / ".tess" / "bin" / "tessctl"
        shutil.copy2(ENGINE_SRC, dst_engine)
        os.chmod(dst_engine, 0o755)

    # -- construction -----------------------------------------------------
    def add(self, live_rel, content="", *, status="core-managed", tier="normal",
            core_key=None, render_live=True, base_sha=None, **extra):
        if core_key is None:
            core_key = ".tess/core/" + live_rel
        data = content.encode("utf-8") if isinstance(content, str) else content
        cp = self.root / core_key
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_bytes(data)
        attrs = {
            "status": status,
            "tier": tier,
            "base_sha": base_sha if base_sha is not None else self.mod.sha256_file(cp),
            "live_path": live_rel,
        }
        attrs.update(extra)
        self.files[core_key] = attrs
        if render_live and live_rel is not None:
            lp = self.root / live_rel
            lp.parent.mkdir(parents=True, exist_ok=True)
            lp.write_bytes(self.mod.render_core_to_live(cp, lp, self.root))
        return core_key

    def stage(self, core_key, content):
        data = content.encode("utf-8") if isinstance(content, str) else content
        sp = self.root / ".tess" / "staging" / core_key
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_bytes(data)
        return sp

    def write_live(self, live_rel, content):
        data = content.encode("utf-8") if isinstance(content, str) else content
        lp = self.root / live_rel
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_bytes(data)
        return lp

    def write(self):
        shutil.copy2(MANIFEST_SRC, self.root / "tess.manifest.json")
        # issue #118: MANIFEST_SRC's own render_targets.enabled is this
        # repo's LIVE, evolving default (["claude-code", "codex"] as of
        # #118) — copying it verbatim would make every synthetic project's
        # enabled-target list silently track whatever this repo currently
        # enables, which is not what most of this suite wants (most fixtures
        # here don't seed codex/generic's own core inputs — AGENTS.md.tpl,
        # its fragments — at all, so a target enabled-by-inheritance fails
        # loud with "template not found" the moment anything renders). Pin
        # every synthetic project back to the historically-stable
        # ["claude-code"] baseline right after the copy; a test that
        # actually wants codex/generic enabled opts in explicitly (see
        # test_render_targets_codex_generic.py's `_set_enabled` helper),
        # exactly like it already seeds that target's own core inputs
        # explicitly rather than inheriting them from this repo's real core.
        manifest_path = self.root / "tess.manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.setdefault("render_targets", {})["enabled"] = ["claude-code"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        lock = {"schema": 1, "framework": self.framework, "files": self.files}
        self.mod.save_lock(self.root, lock)
        return self.mod.load_lock(self.root)

    # -- path helpers -----------------------------------------------------
    def live(self, rel):
        return self.root / rel

    def core(self, core_key):
        return self.root / core_key

    def staging_path(self, core_key):
        return self.root / ".tess" / "staging" / core_key

    def read_live(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def lock(self):
        return self.mod.load_lock(self.root)


@pytest.fixture
def project(tmp_path, engine):
    """A fresh synthetic Tess OS project rooted at tmp_path."""
    return Project(tmp_path, engine)


# ---------------------------------------------------------------------------
# CLI runner (subprocess — exercises main(), argparse, exit codes, tool checks)
# ---------------------------------------------------------------------------


@pytest.fixture
def run_cli():
    def _run(root, *args, input_text=None, extra_env=None):
        env = {**os.environ, "TESS_ROOT": str(root)}
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
            cwd=str(root), env=env, capture_output=True, text=True,
            input=input_text,
        )

    return _run


def ns(**kw):
    """Build an argparse-like namespace for direct cmd_* calls."""
    return types.SimpleNamespace(**kw)


# ---------------------------------------------------------------------------
# GPG signing key + signed-upstream builder (for FETCH + self-update)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def gpg_key():
    """Generate a throwaway GPG key in an isolated GNUPGHOME.

    Sets GNUPGHOME for the whole session so git subprocesses inside
    fetch_to_staging / self-update inherit the keyring. Skips if gpg absent.

    NOTE: GNUPGHOME lives under /tmp with a short prefix, NOT pytest's deep
    tmp_path — the gpg-agent UNIX socket path has a ~104-char limit and pytest's
    nested tmp dirs blow past it ("File name too long" → no agent → keygen fails).
    """
    import tempfile

    if not (HAS_GPG and HAS_GIT):
        pytest.skip("gpg + git required for signature tests")

    home = Path(tempfile.mkdtemp(prefix="tessgpg", dir="/tmp"))
    os.chmod(home, 0o700)
    params = home / "keyparams"
    params.write_text(
        "%no-protection\n"
        "Key-Type: eddsa\n"
        "Key-Curve: ed25519\n"
        "Key-Usage: sign\n"
        "Name-Real: Tess Test Signer\n"
        "Name-Email: signer@tess.test\n"
        "Expire-Date: 0\n"
        "%commit\n"
    )
    env = {**os.environ, "GNUPGHOME": str(home)}
    r = subprocess.run(["gpg", "--batch", "--gen-key", str(params)],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        pytest.skip(f"gpg key generation failed: {r.stderr}")
    lk = subprocess.run(["gpg", "--list-keys", "--with-colons", "signer@tess.test"],
                        capture_output=True, text=True, env=env)
    fpr = ""
    for line in lk.stdout.splitlines():
        if line.startswith("fpr:"):
            fpr = line.split(":")[9]
            break
    if not fpr:
        pytest.skip("could not extract GPG fingerprint")

    prev = os.environ.get("GNUPGHOME")
    os.environ["GNUPGHOME"] = str(home)
    yield types.SimpleNamespace(home=str(home), fpr=fpr, email="signer@tess.test")
    # Teardown: stop the agent holding the home open, then remove it.
    subprocess.run(["gpgconf", "--homedir", str(home), "--kill", "gpg-agent"],
                   capture_output=True, env={**os.environ, "GNUPGHOME": str(home)})
    if prev is None:
        os.environ.pop("GNUPGHOME", None)
    else:
        os.environ["GNUPGHOME"] = prev
    shutil.rmtree(home, ignore_errors=True)


# ---------------------------------------------------------------------------
# Per-verifier GPG identities (Phase 2b — verdict signing tests)
#
# Deliberately INDEPENDENT of `gpg_key` above (no shared refactor of that
# already-shipped, tier-tested fixture — same "don't touch a proven subsystem
# for an unrelated feature" discipline `_gate_install_git_hooks`'s own module
# comment already documents for the hook-splice code). Each verifier gets its
# OWN isolated GNUPGHOME + real keypair, so a test can prove "verifier X's
# signature does not clear a rule scoped to verifier Y" with two genuinely
# distinct keys, not just two different `verifier:` string values signed by
# the same key.
# ---------------------------------------------------------------------------

def _gen_verifier_gpg_identity(name: str):
    """Generate one throwaway ed25519 GPG keypair for verifier `name`, in its
    own isolated GNUPGHOME. Returns a SimpleNamespace(home, fpr,
    pubkey_armored, email) or raises pytest.skip if gpg is unavailable/fails
    (mirrors `gpg_key`'s own skip behavior)."""
    import tempfile

    home = Path(tempfile.mkdtemp(prefix=f"tessgpgv{name.lower()[:4]}", dir="/tmp"))
    os.chmod(home, 0o700)
    email = f"{name.lower()}@tess.test"
    params = home / "keyparams"
    params.write_text(
        "%no-protection\n"
        "Key-Type: eddsa\n"
        "Key-Curve: ed25519\n"
        "Key-Usage: sign\n"
        f"Name-Real: Tess Test Verifier {name}\n"
        f"Name-Email: {email}\n"
        "Expire-Date: 0\n"
        "%commit\n"
    )
    env = {**os.environ, "GNUPGHOME": str(home)}
    r = subprocess.run(["gpg", "--batch", "--gen-key", str(params)],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        shutil.rmtree(home, ignore_errors=True)
        pytest.skip(f"gpg key generation failed for verifier {name}: {r.stderr}")
    lk = subprocess.run(["gpg", "--list-keys", "--with-colons", email],
                        capture_output=True, text=True, env=env)
    fpr = ""
    for line in lk.stdout.splitlines():
        if line.startswith("fpr:"):
            fpr = line.split(":")[9]
            break
    if not fpr:
        shutil.rmtree(home, ignore_errors=True)
        pytest.skip(f"could not extract GPG fingerprint for verifier {name}")
    exp = subprocess.run(["gpg", "--homedir", str(home), "--export", "--armor", fpr],
                         capture_output=True, text=True, env=env)
    return types.SimpleNamespace(home=home, fpr=fpr, pubkey_armored=exp.stdout, email=email)


_VERIFIER_NAMES_FOR_TESTS = ("Reid", "Quinn", "Cyra", "Verity", "Maialen", "Lysandra")


@pytest.fixture(scope="session")
def verifier_gpg_keys():
    """{verifier-name: SimpleNamespace(home, fpr, pubkey_armored, email)} for
    all six named verifiers, each a REAL, independent GPG keypair in its own
    isolated GNUPGHOME. Session-scoped (keygen is slow) — skips the whole
    session if gpg is unavailable."""
    if not (HAS_GPG and HAS_GIT):
        pytest.skip("gpg + git required for verdict-signature tests")
    keys = {name: _gen_verifier_gpg_identity(name) for name in _VERIFIER_NAMES_FOR_TESTS}
    yield keys
    for key in keys.values():
        subprocess.run(["gpgconf", "--homedir", str(key.home), "--kill", "gpg-agent"],
                       capture_output=True, env={**os.environ, "GNUPGHOME": str(key.home)})
        shutil.rmtree(str(key.home), ignore_errors=True)


@pytest.fixture(scope="session")
def signoff_gpg_key():
    """One real, isolated operator key distinct from every verifier primary.

    Human hard-floor authority and AI review authority are separate trust
    domains even for a solo operator. Tests therefore model Xavier with a
    seventh ephemeral primary instead of aliasing Reid's certificate.
    """
    if not (HAS_GPG and HAS_GIT):
        pytest.skip("gpg + git required for signoff-signature tests")
    key = _gen_verifier_gpg_identity("Xavier")
    yield key
    subprocess.run(
        ["gpgconf", "--homedir", str(key.home), "--kill", "gpg-agent"],
        capture_output=True, env={**os.environ, "GNUPGHOME": str(key.home)},
    )
    shutil.rmtree(str(key.home), ignore_errors=True)


def sign_verdict_for_test(engine, verdict: dict, key) -> dict:
    """Produce a `signature` block for `verdict`, signed by GPG identity
    `key` (a SimpleNamespace from `verifier_gpg_keys` / `gpg_key`) — using
    the ENGINE's own `verdict_canonical_bytes()` so the test signs exactly
    the same canonical form `tessctl gate` will recompute at verify time."""
    canonical = engine.verdict_canonical_bytes(verdict)
    content_hash = hashlib.sha256(canonical).hexdigest()
    env = {**os.environ, "GNUPGHOME": str(key.home)}
    r = subprocess.run(
        ["gpg", "--homedir", str(key.home), "--batch", "--yes",
         "--local-user", key.fpr, "--detach-sign", "--armor", "--output", "-"],
        input=canonical, capture_output=True, env=env,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", errors="replace")
    return {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": content_hash,
        "signature_armored": r.stdout.decode("utf-8"),
    }


def sign_signoff_for_test(engine, signoff: dict, key) -> dict:
    """Twin of `sign_verdict_for_test` for hard-floor sign-off artifacts
    (honesty-capstone-audit-2026-07-08 §3-d) — produces a `signature` block
    for `signoff`, signed by GPG identity `key`, using the ENGINE's own
    `signoff_canonical_bytes()` so the test signs exactly the same canonical
    form `tessctl gate` will recompute at verify time. `key` need not be one
    of the six named AI verifiers — a sign-off's `authorized_by` is an
    arbitrary human-operator identity, so any generated test GPG identity
    (e.g. one of `verifier_gpg_keys`'s entries, reused under a different
    registered name) works fine here."""
    canonical = engine.signoff_canonical_bytes(signoff)
    content_hash = hashlib.sha256(canonical).hexdigest()
    env = {**os.environ, "GNUPGHOME": str(key.home)}
    r = subprocess.run(
        ["gpg", "--homedir", str(key.home), "--batch", "--yes",
         "--local-user", key.fpr, "--detach-sign", "--armor", "--output", "-"],
        input=canonical, capture_output=True, env=env,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", errors="replace")
    return {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": content_hash,
        "signature_armored": r.stdout.decode("utf-8"),
    }


def make_upstream(path: Path, gpg, tag, *, sign="signed",
                  core_files=None, engine_bytes=None,
                  lock_files=None, symlinks=None, unsafe_paths=False):
    """Create a git repo at `path` that looks like a Tess OS upstream and tag it.

    sign: "signed"      → git tag -s   (annotated + GPG signature)
          "annotated"   → git tag -a   (annotated, NO signature)
          "lightweight" → git tag      (no tag object at all)
    core_files: {rel_path: text} written under .tess/core/
    engine_bytes: if given, written to .tess/bin/tessctl
    lock_files: {core_key: attrs} → written as .tess/tess.lock (the upstream lock
                fetch_to_staging copies to staging/upstream-tess.lock for A2
                new-file adoption). attrs need at least 'live_path'.
    symlinks: {link_rel: target} → symlinks created in the tree (e.g. a poisoned
              entry under .tess/core/ to exercise the C2 symlink-extraction guard).
    unsafe_paths: when True, `git add` runs with protectHFS/protectNTFS disabled so
                  poisoned paths (e.g. a '.git.' trailing-dot component) can be
                  committed to the upstream for the C4 rejection test.
    """
    path.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GNUPGHOME": gpg.home}

    def git(*a, check=True):
        r = subprocess.run(["git", "-C", str(path), *a],
                           capture_output=True, text=True, env=env)
        if check and r.returncode != 0:
            raise RuntimeError(f"git {' '.join(a)} failed: {r.stderr}")
        return r

    git("init", "-q")
    git("config", "user.email", gpg.email)
    git("config", "user.name", "Tess Test Signer")
    git("config", "user.signingkey", gpg.fpr)
    git("config", "gpg.format", "openpgp")
    git("config", "commit.gpgsign", "false")

    core_files = core_files or {".tess/core/conductor/guardrails.md": "guardrails upstream\n"}
    for rel, text in core_files.items():
        fp = path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(text)
    if engine_bytes is not None:
        ep = path / ".tess" / "bin" / "tessctl"
        ep.parent.mkdir(parents=True, exist_ok=True)
        ep.write_bytes(engine_bytes)

    if symlinks:
        for link_rel, target in symlinks.items():
            lp = path / link_rel
            lp.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(target, lp)

    if lock_files is not None:
        lock_obj = {
            "schema": 1,
            "framework": {
                "track": "v2",
                "version": tag.lstrip("v"),
                "upstream_ref": tag,
                "trusted_key_fingerprint": "",
            },
            "files": lock_files,
        }
        lp = path / ".tess" / "tess.lock"
        lp.parent.mkdir(parents=True, exist_ok=True)
        # JSON is valid YAML — the engine reads tess.lock with yaml.safe_load.
        lp.write_text(json.dumps(lock_obj, indent=2), encoding="utf-8")

    if unsafe_paths:
        git("-c", "core.protectHFS=false", "-c", "core.protectNTFS=false", "add", "-A")
    else:
        git("add", "-A")
    git("commit", "-q", "-m", "upstream release")

    if sign == "signed":
        git("tag", "-s", tag, "-m", f"signed {tag}")
    elif sign == "annotated":
        git("tag", "-a", tag, "-m", f"annotated unsigned {tag}")
    elif sign == "lightweight":
        git("tag", tag)
    else:
        raise ValueError(sign)
    return path


def corrupt_tag_signature(repo_path: Path, tag: str) -> None:
    """Tamper an ALREADY-SIGNED annotated tag in place, in `repo_path` (built by
    `make_upstream(..., sign="signed")`).

    Flips one byte inside the tag object's armored PGP signature block, then
    repoints `refs/tags/<tag>` at the corrupted object (`git hash-object -t tag
    -w --stdin` + `git update-ref`). The corrupted object is STILL a
    well-formed annotated tag — `git cat-file -t <tag>` keeps reporting "tag"
    (so C4's "is an annotated tag object" check still passes) — but
    `git verify-tag` fails (BADSIG/NODATA), because the signature bytes no
    longer match what was actually signed.

    This is deliberately a THIRD, distinct security scenario from the suite's
    existing coverage:
      * unsigned tag (test_mandatory_pin.py)   → no signature at all
      * wrong-key tag (test_mandatory_pin.py)  → valid signature, untrusted key
      * tampered tag (this helper)              → well-formed tag object,
                                                    invalid/corrupted signature
    """
    raw = subprocess.run(
        ["git", "-C", str(repo_path), "cat-file", "tag", tag],
        capture_output=True, check=True,
    ).stdout
    idx = raw.find(b"-----BEGIN PGP SIGNATURE-----")
    assert idx != -1, "corrupt_tag_signature: no armored PGP signature block found on tag"
    body_start = raw.find(b"\n", idx) + 1
    flip_pos = body_start + 40  # well inside the base64 body, not the header/footer markers
    corrupted = bytearray(raw)
    corrupted[flip_pos] ^= 0xFF
    new_hash = subprocess.run(
        ["git", "-C", str(repo_path), "hash-object", "-t", "tag", "-w", "--stdin"],
        input=bytes(corrupted), capture_output=True, check=True,
    ).stdout.decode().strip()
    subprocess.run(
        ["git", "-C", str(repo_path), "update-ref", f"refs/tags/{tag}", new_hash],
        check=True,
    )
