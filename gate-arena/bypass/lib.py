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
FORKS the real, current `core/policy/policy.yaml` (verbatim `rules`,
`hard_floor_rules`, and the `tess-os-security-tier-doctrine` self-gating
globs) and only ADDS one ordinary rule (`prod-src`, for tests that need a
non-self-referential path to gate) plus real generated keys for Reid/Cyra/
Quinn (current main already registers Cyra's public key; the fixture replaces
the registry with throwaway test-only public identities so every signed test
is isolated and reproducible). This is not a synthetic invention:
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
    fpr, expire_epoch = "", None
    for line in lk.stdout.splitlines():
        fields = line.split(":")
        if fields[0] == "pub" and len(fields) > 6 and fields[6]:
            # honesty-capstone-audit-2026-07-08 P0 arena-fixture fix: record
            # the KEY'S OWN recorded expiration epoch (colon-listing field 6)
            # so a caller needing an already-expired key can wait it out
            # deterministically (see attack_A10_shape_attacks' expired_key
            # sub-attack) — gpg batch keygen does NOT accept a literal
            # already-past absolute date (e.g. "20200101") the way the
            # original A10c arena fixture assumed; it silently produces an
            # ~immediate-expiry key instead of the intended year-2020 one,
            # which made that sub-attack SLIP for the wrong reason (a broken
            # fixture, not a real engine gap) even against an engine that
            # already closed A10c. `Expire-Date: seconds=N` (a real gpg
            # batch-keygen relative-offset syntax) + waiting for
            # `expire_epoch` to actually pass is the same technique
            # tests/test_verdict_signing.py's own A10c proof already uses.
            expire_epoch = int(fields[6])
        if fields[0] == "fpr":
            fpr = fields[9]
    if not fpr:
        raise RuntimeError(f"could not extract fingerprint for {name}")
    exp = subprocess.run(["gpg", "--homedir", str(home), "--export", "--armor", fpr],
                         capture_output=True, text=True, env=env)
    return types.SimpleNamespace(
        home=home, fpr=fpr, pubkey_armored=exp.stdout, email=email, name=name,
        expire_epoch=expire_epoch,
    )


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
# honesty-capstone-audit-2026-07-08 §3-d — hard-floor sign-off signing
# helpers (attack A12). Twins of sign_verdict/bundle_key/write_signoff
# above, applied to the sign-off authentication path instead of verdicts.
# ---------------------------------------------------------------------------

def sign_signoff(engine, signoff: dict, key) -> dict:
    """Twin of sign_verdict() — signs the engine's own
    `signoff_canonical_bytes()` output so it is byte-identical to what
    `tessctl gate` recomputes at verify time."""
    canonical = engine.signoff_canonical_bytes(signoff)
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


def bundle_signoff_key(root: Path, name: str, key) -> str:
    keys_dir = root / ".tess" / "keys" / "signoffs"
    keys_dir.mkdir(parents=True, exist_ok=True)
    (keys_dir / f"{name.lower()}.asc").write_text(key.pubkey_armored, encoding="utf-8")
    return f".tess/keys/signoffs/{name.lower()}.asc"


def write_forged_signoff(root: Path, rule_id: str, category: str, authorized_by: str, rationale: str) -> Path:
    """An UNSIGNED, shape-valid-only sign-off — exactly what any agent able
    to write a file could forge pre-(d)-fix, and exactly what
    `write_signoff` above (A2) also writes. Named distinctly here (A12
    reuses this construction deliberately, not by coincidence) to make the
    forgery explicit at the call site."""
    p = root / ".tess" / "gate" / "signoffs" / f"{rule_id}.signoff.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "rule_id": rule_id,
        "category": category,
        "authorized_by": authorized_by,
        "rationale": rationale,
        "authorized_at": "2026-07-08T00:00:00Z",
    }, indent=2), encoding="utf-8")
    return p


def write_signed_signoff(root: Path, rule_id: str, category: str, authorized_by: str,
                          rationale: str, engine, key) -> Path:
    """A genuinely, cryptographically signed sign-off — the (d)-fix's real,
    satisfiable escape valve."""
    signoff = {
        "rule_id": rule_id,
        "category": category,
        "authorized_by": authorized_by,
        "rationale": rationale,
        "authorized_at": "2026-07-08T00:00:00Z",
    }
    signoff["signature"] = sign_signoff(engine, signoff, key)
    p = root / ".tess" / "gate" / "signoffs" / f"{rule_id}.signoff.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(signoff, indent=2), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# The fixture repo itself
# ---------------------------------------------------------------------------

def _forked_policy_dict(verifier_keys: dict, signoff_keys: dict = None) -> dict:
    """Load the REAL, current core/policy/policy.yaml and only
    (a) replace verifier_keys with isolated throwaway arena identities,
    (a2) populate signoff_keys likewise (honesty-capstone-audit-2026-07-08
    §3-d; current source signoff_keys is empty), and (b) add one
    ordinary, non-self-referential rule (`prod-src`) so attacks that need a
    plain application-code path to gate have one, without inventing a
    synthetic self-gating policy. The real `tess-os-security-tier-doctrine`
    rule (which already covers `core/policy/**`, `.github/workflows/**` —
    MEDIUM-1 — and, as of §3-c/§3-d, `.tess/bin/**` + `tessctl` +
    `.tess/gate/signoffs/**`) and all four real `hard_floor_rules` travel
    through UNCHANGED."""
    real = yaml.safe_load(REAL_POLICY_SRC.read_text(encoding="utf-8"))
    policy = real["policy"]
    policy["verifier_keys"] = verifier_keys
    policy["signoff_keys"] = signoff_keys or {}
    policy["rules"] = list(policy["rules"]) + [{
        "id": "prod-src",
        "description": "Gate-arena fixture rule — ordinary application code, non-self-referential.",
        "globs": ["src/prod/**"],
        "classification": ["prod_touching"],
        "require_verdict": True,
        "allowed_verifiers": ["Quinn"],
    }]
    return {"policy": policy}


# ---------------------------------------------------------------------------
# honesty-capstone-audit-2026-07-08 §3-c — trusted-engine CI simulation
# (attack A11). Parses and EXECUTES the real, COMMITTED `.github/workflows/
# tess-gate.yml` from THIS repo checkout's own steps (not a
# reimplementation) — same technique tests/test_gate_engine_selfprotect.py
# uses — so this arena proves the ACTUAL shipped CI defense, not a mock of
# it.
# ---------------------------------------------------------------------------

REAL_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "tess-gate.yml"


def _extract_workflow_step_run(workflow_text: str, step_name: str) -> str:
    doc = yaml.safe_load(workflow_text)
    for step in doc["jobs"]["ship-gate"]["steps"]:
        if step.get("name") == step_name:
            return step["run"]
    raise KeyError(step_name)


def run_ci_workflow_trusted_engine(root: Path, base: str, head: str):
    """Runs the REAL, committed `.github/workflows/tess-gate.yml`'s own
    "Extract trusted gate engine" + final "tessctl gate ci" run: blocks
    against `root` (a real git repo with real history at `base`/`head`),
    substituting the GH Actions expressions this harness needs with literal
    values / a real $GITHUB_OUTPUT file. Returns (returncode, combined
    stdout+stderr). If the fix is ever reverted (the trusted-engine step
    removed), `_extract_workflow_step_run` raises KeyError."""
    workflow_text = REAL_WORKFLOW_PATH.read_text(encoding="utf-8")
    extract_script = _extract_workflow_step_run(
        workflow_text, "Extract trusted gate engine (base ref only — never the pushed tree)",
    )
    ci_script = _extract_workflow_step_run(
        workflow_text, "tessctl gate ci (trusted base-ref engine; untrusted pushed tree)",
    )

    extract_script = extract_script.replace("${{ steps.refs.outputs.base }}", base)
    gh_output_path = Path(tempfile.mkstemp(prefix="gh_output_")[1])
    gh_output_path.write_text("")
    env1 = {**os.environ, "GITHUB_OUTPUT": str(gh_output_path)}
    r1 = subprocess.run(["bash", "-c", extract_script], cwd=str(root), env=env1, capture_output=True, text=True)
    if r1.returncode != 0:
        return r1.returncode, r1.stdout + r1.stderr

    outputs = {}
    for line in gh_output_path.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            outputs[k] = v
    gh_output_path.unlink(missing_ok=True)
    engine_path = outputs.get("engine_path")
    if not engine_path:
        return 1, f"extract step did not emit engine_path — stdout/stderr: {r1.stdout}{r1.stderr}"

    ci_script2 = (
        ci_script
        .replace("${{ steps.trusted_engine.outputs.engine_path }}", engine_path)
        .replace("${{ steps.refs.outputs.base }}", base)
        .replace("${{ steps.refs.outputs.head }}", head)
    )
    env2 = {**os.environ, "TESS_ROOT": str(root)}
    r2 = subprocess.run(["bash", "-c", ci_script2], cwd=str(root), env=env2, capture_output=True, text=True)
    return r2.returncode, r2.stdout + r2.stderr


def run_cli_with_engine(root: Path, engine_path: str, *args, env_extra=None):
    """Twin of run_cli() that invokes an EXPLICIT engine path rather than
    always `root/.tess/bin/tessctl` — used to run the pushed tree's own
    (possibly tampered) engine directly, exactly what the v2/unpatched CI
    workflow did before the §3-c trusted-engine fix."""
    env = {**os.environ, "TESS_ROOT": str(root)}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(engine_path), *args],
        cwd=str(root), env=env, capture_output=True, text=True,
    )


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

        # honesty-capstone-audit-2026-07-08 §3-d: a real, generated
        # sign-off-authorizer identity ("Xavier") registered in
        # policy.signoff_keys, so attack A12 can prove BOTH "an unsigned/
        # forged sign-off does not clear" AND "a properly signed one does."
        self.keys["Xavier"] = gen_verifier_key("Xavier", self.gpg_base)
        signoff_rel = bundle_signoff_key(self.root, "Xavier", self.keys["Xavier"])
        signoff_keys = {"Xavier": {"fingerprint": self.keys["Xavier"].fpr, "public_key_file": signoff_rel}}

        policy_dict = _forked_policy_dict(verifier_keys, signoff_keys)
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

    def sign_signoff_as(self, signoff: dict, authorizer_name: str) -> dict:
        return sign_signoff(self.engine, signoff, self.keys[authorizer_name])

    def gate_ci(self, base: str, head: str, json_out=True):
        args = ["gate", "ci", "--base", base, "--head", head]
        if json_out:
            args.append("--json")
        r = run_cli(self.root, *args)
        payload = json.loads(r.stdout) if json_out and r.stdout.strip() else None
        return r, payload

    def gate_ci_naive_with_pushed_engine(self, base: str, head: str, json_out=True):
        """honesty-capstone-audit-2026-07-08 §3-c: runs the PUSHED tree's
        OWN copy of .tess/bin/tessctl directly — exactly what the v2/
        unpatched CI workflow did before the trusted-engine fix. Used to
        prove a same-push engine tamper slips past this naive invocation
        (attack A11)."""
        args = ["gate", "ci", "--base", base, "--head", head]
        if json_out:
            args.append("--json")
        r = run_cli_with_engine(self.root, self.root / ".tess" / "bin" / "tessctl", *args)
        payload = json.loads(r.stdout) if json_out and r.stdout.strip() else None
        return r, payload

    def gate_ci_via_real_ci_workflow(self, base: str, head: str):
        """honesty-capstone-audit-2026-07-08 §3-c: runs the REAL, committed
        `.github/workflows/tess-gate.yml`'s own trusted-engine steps against
        this fixture repo. Returns (returncode, combined stdout+stderr) —
        NOT a JSON payload, since this executes the real shell script end to
        end, exactly the way GitHub Actions would."""
        return run_ci_workflow_trusted_engine(self.root, base, head)
