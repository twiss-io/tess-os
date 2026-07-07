"""
gate-arena/bypass/lib.py — shared fixture-repo + GPG helpers for the Layer A
bypass corpus. Standalone (no pytest dependency) so the arena is a plain
`python3` script, re-runnable end-to-end against a real fixture repo, real
`git`, real `gpg`, and the REAL `.tess/bin/tessctl` engine copied verbatim
from this repo's own `main` branch — not a reimplementation or a mock.

Patterns below are deliberately modeled on tests/conftest.py's own
`verifier_gpg_keys` / `sign_verdict_for_test` / `_policy_dict` fixtures (the
project's existing, already-reviewed gate-testing idiom) rather than
inventing a new one — the arena is meant to demonstrate the SAME engine the
unit tests already exercise, just end-to-end and publicly re-runnable rather
than pytest-internal.

Key design choice worth stating up front: this arena's fixture policy
FORKS the real, shipped `core/policy/policy.yaml` (verbatim `rules`,
`hard_floor_rules`, and the `tess-os-security-tier-doctrine` self-gating
globs) and only ADDS one ordinary rule (`prod-src`, for tests that need a
non-self-referential path to gate) plus real generated keys for Reid/Cyra/
Quinn (the shipped file deliberately ships `verifier_keys: {}` — see its own
header comment — so a fresh arena run has to onboard real keys before any
of the self-gating tests mean anything). This is not a synthetic invention:
attacks 3 and 8 below test THIS repo's actual shipped self-protection glob
list, not a toy policy.
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
import tempfile
import types
from pathlib import Path

import yaml

ARENA_ROOT = Path(__file__).resolve().parent.parent          # gate-arena/
REPO_ROOT = ARENA_ROOT.parent                                  # tess-os/ (this checkout)
ENGINE_SRC = REPO_ROOT / ".tess" / "bin" / "tessctl"
CONTRACTS_SRC = REPO_ROOT / "core" / "contracts"
REAL_POLICY_SRC = REPO_ROOT / "core" / "policy" / "policy.yaml"

VERIFIER_NAMES = ("Reid", "Quinn", "Cyra", "Verity", "Maialen", "Lysandra")

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "Gate Arena",
    "GIT_AUTHOR_EMAIL": "arena@tess-os.test",
    "GIT_COMMITTER_NAME": "Gate Arena",
    "GIT_COMMITTER_EMAIL": "arena@tess-os.test",
}


def load_engine():
    """Import the REAL .tess/bin/tessctl (no extension) as a module, exactly
    the way tests/conftest.py's `engine` fixture does. Loading never
    executes main() (guarded by `if __name__ == "__main__"` in the engine)."""
    loader = importlib.machinery.SourceFileLoader("tessctl_arena_engine", str(ENGINE_SRC))
    spec = importlib.util.spec_from_loader("tessctl_arena_engine", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def git(root: Path, *args, check=True, input_text=None, env_extra=None):
    env = {**os.environ, **_GIT_ENV}
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, env=env, input=input_text,
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed (rc={r.returncode}):\n{r.stderr}\n{r.stdout}")
    return r


def init_repo(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "arena@tess-os.test")
    git(root, "config", "user.name", "Gate Arena")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "receive.denyCurrentBranch", "updateInstead")


def commit_all(root: Path, message: str) -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD").stdout.strip()


def head_sha(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").stdout.strip()


def blob_sha(root: Path, rel_path: str) -> str:
    return git(root, "hash-object", rel_path).stdout.strip()


def run_cli(root: Path, *args, env_extra=None):
    """Real subprocess invocation of THIS fixture repo's own copy of
    tessctl — exercises argparse, exit codes, and stdout exactly the way a
    real operator or CI job would, not a direct function call."""
    env = {**os.environ, "TESS_ROOT": str(root)}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(root / ".tess" / "bin" / "tessctl"), *args],
        cwd=str(root), env=env, capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# GPG verifier identities (real, throwaway, per-run)
# ---------------------------------------------------------------------------

def gen_verifier_key(name: str, gpg_base: Path, expire: str = "0"):
    """Generate one real ed25519 GPG keypair for verifier `name` in its own
    isolated GNUPGHOME. Deliberately ignores `gpg_base` for the actual
    homedir location and always creates it directly under `/tmp` with a
    SHORT prefix — gpg-agent's UNIX socket has a ~104-char path limit, and
    this arena's own scratch dirs (under macOS's deep
    /var/folders/.../T/gate-arena-bypass-<id>/<attack>/gpg/... tree) blow
    past that limit if GNUPGHOME is nested inside them (confirmed
    empirically: first run of this exact code failed every attack with
    "agent_genkey failed: No agent running" / "File name too long" — same
    failure mode conftest.py's own `gpg_key`/`_gen_verifier_gpg_identity`
    fixtures already document and avoid the same way)."""
    home = Path(tempfile.mkdtemp(prefix=f"tga{name.lower()[:3]}", dir="/tmp"))
    os.chmod(home, 0o700)
    email = f"{name.lower()}@tess-os.test"
    params = home / "keyparams"
    params.write_text(
        "%no-protection\n"
        "Key-Type: eddsa\n"
        "Key-Curve: ed25519\n"
        "Key-Usage: sign\n"
        f"Name-Real: Gate Arena Verifier {name}\n"
        f"Name-Email: {email}\n"
        f"Expire-Date: {expire}\n"
        "%commit\n"
    )
    env = {**os.environ, "GNUPGHOME": str(home)}
    r = subprocess.run(["gpg", "--batch", "--gen-key", str(params)], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"gpg keygen failed for {name}: {r.stderr}")
    lk = subprocess.run(["gpg", "--list-keys", "--with-colons", email], capture_output=True, text=True, env=env)
    fpr = ""
    for line in lk.stdout.splitlines():
        if line.startswith("fpr:"):
            fpr = line.split(":")[9]
            break
    if not fpr:
        raise RuntimeError(f"could not extract fingerprint for {name}")
    exp = subprocess.run(["gpg", "--homedir", str(home), "--export", "--armor", fpr],
                         capture_output=True, text=True, env=env)
    return types.SimpleNamespace(home=home, fpr=fpr, pubkey_armored=exp.stdout, email=email, name=name)


def kill_gpg_agent(key):
    subprocess.run(["gpgconf", "--homedir", str(key.home), "--kill", "gpg-agent"],
                   capture_output=True, env={**os.environ, "GNUPGHOME": str(key.home)})
    shutil.rmtree(str(key.home), ignore_errors=True)


def sign_verdict(engine, verdict: dict, key) -> dict:
    """Same construction as conftest.py's `sign_verdict_for_test` — signs the
    engine's own `verdict_canonical_bytes()` output so it is byte-identical
    to what `tessctl gate` recomputes at verify time."""
    canonical = engine.verdict_canonical_bytes(verdict)
    content_hash = hashlib.sha256(canonical).hexdigest()
    env = {**os.environ, "GNUPGHOME": str(key.home)}
    r = subprocess.run(
        ["gpg", "--homedir", str(key.home), "--batch", "--yes",
         "--local-user", key.fpr, "--detach-sign", "--armor", "--output", "-"],
        input=canonical, capture_output=True, env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gpg sign failed: {r.stderr.decode('utf-8', errors='replace')}")
    return {
        "algorithm": "gpg-detached-armor",
        "signed_content_sha256": content_hash,
        "signature_armored": r.stdout.decode("utf-8"),
    }


def bundle_key(root: Path, name: str, key) -> str:
    keys_dir = root / ".tess" / "keys" / "verifiers"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / f"{name.lower()}.asc").write_text(key.pubkey_armored, encoding="utf-8")
    return f".tess/keys/verifiers/{name.lower()}.asc"


def base_verdict(covers_paths, artifact_hashes, verifier="Reid") -> dict:
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


def write_verdict(root: Path, rel_path: str, verdict_dict: dict) -> Path:
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\n" + yaml.safe_dump(verdict_dict) + "---\n\n# Verdict body\n", encoding="utf-8")
    return p


def write_signoff(root: Path, rule_id: str, category: str, rationale: str) -> Path:
    p = root / ".tess" / "gate" / "signoffs" / f"{rule_id}.signoff.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "rule_id": rule_id,
        "category": category,
        "authorized_by": "Xavier (arena fixture — simulated hard-floor sign-off)",
        "rationale": rationale,
        "authorized_at": "2026-07-08T00:00:00Z",
    }, indent=2), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# The fixture repo itself
# ---------------------------------------------------------------------------

def _forked_policy_dict(verifier_keys: dict) -> dict:
    """Load the REAL, shipped core/policy/policy.yaml verbatim and only
    (a) populate verifier_keys (shipped empty on purpose — see the file's
    own header) and (b) add one ordinary, non-self-referential rule
    (`prod-src`) so attacks that need a plain application-code path to gate
    have one, without inventing a synthetic self-gating policy. The real
    `tess-os-security-tier-doctrine` rule (which already covers
    `core/policy/**` and `.github/workflows/**` — MEDIUM-1) and all four
    real `hard_floor_rules` travel through UNCHANGED."""
    real = yaml.safe_load(REAL_POLICY_SRC.read_text(encoding="utf-8"))
    policy = real["policy"]
    policy["verifier_keys"] = verifier_keys
    policy["rules"] = list(policy["rules"]) + [{
        "id": "prod-src",
        "description": "Gate-arena fixture rule — ordinary application code, non-self-referential.",
        "globs": ["src/prod/**"],
        "classification": ["prod_touching"],
        "require_verdict": True,
        "allowed_verifiers": ["Quinn"],
    }]
    return {"policy": policy}


class FixtureRepo:
    """A throwaway git repo with the REAL engine, REAL contract schemas, and
    a policy forked from the REAL shipped core/policy/policy.yaml (see
    `_forked_policy_dict`). `keys` maps verifier name -> gpg identity for
    Reid, Cyra, Quinn (real, generated fresh per arena run)."""

    def __init__(self, base_dir: Path, engine):
        self.root = base_dir / "repo"
        self.gpg_base = base_dir / "gpg"
        self.gpg_base.mkdir(parents=True, exist_ok=True)
        self.engine = engine
        self.keys = {}

        init_repo(self.root)

        # Real engine, real contracts.
        (self.root / ".tess" / "bin").mkdir(parents=True, exist_ok=True)
        shutil.copy2(ENGINE_SRC, self.root / ".tess" / "bin" / "tessctl")
        os.chmod(self.root / ".tess" / "bin" / "tessctl", 0o755)
        shutil.copytree(CONTRACTS_SRC, self.root / "core" / "contracts")

        # Real verifier keys for the three names this fixture's policy names.
        for name in ("Reid", "Cyra", "Quinn"):
            self.keys[name] = gen_verifier_key(name, self.gpg_base)

        verifier_keys = {}
        for name, key in self.keys.items():
            rel = bundle_key(self.root, name, key)
            verifier_keys[name] = {"fingerprint": key.fpr, "public_key_file": rel}

        policy_dict = _forked_policy_dict(verifier_keys)
        (self.root / "core" / "policy").mkdir(parents=True, exist_ok=True)
        (self.root / "core" / "policy" / "policy.yaml").write_text(
            yaml.safe_dump(policy_dict, sort_keys=False), encoding="utf-8",
        )

        # A minimal ordinary source file the "prod-src" rule can gate.
        (self.root / "src" / "prod").mkdir(parents=True, exist_ok=True)
        (self.root / "src" / "prod" / "app.py").write_text("print('prod v1')\n", encoding="utf-8")

        self.base_sha = commit_all(self.root, "gate-arena fixture: real engine + real forked policy + prod-src v1")

    def teardown(self):
        for key in self.keys.values():
            kill_gpg_agent(key)

    # -- convenience --------------------------------------------------------
    def install_hooks(self):
        r = run_cli(self.root, "gate", "install-hooks")
        if r.returncode != 0:
            raise RuntimeError(f"install-hooks failed: {r.stdout}\n{r.stderr}")
        return r

    def sign(self, verdict: dict, verifier_name: str) -> dict:
        return sign_verdict(self.engine, verdict, self.keys[verifier_name])

    def gate_ci(self, base: str, head: str, json_out=True):
        args = ["gate", "ci", "--base", base, "--head", head]
        if json_out:
            args.append("--json")
        r = run_cli(self.root, *args)
        payload = json.loads(r.stdout) if json_out and r.stdout.strip() else None
        return r, payload
