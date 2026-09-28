"""v0.2.1 install fixes: tessctl without PyYAML, and a path-scoped seed commit.

1. Stock macOS /usr/bin/python3 (3.9) has no PyYAML. `python3 -S -I` drops
   site-packages and every PYTHON* variable, which is the same situation, so
   tessctl must still run doctor/verify from its vendored PyYAML.
2. npm strips .gitignore from the create-tess tarball. Onboarding's first
   commit used `git add -A`, which then staged operator/profile.json and .env,
   the publish-clean pre-commit gate refused them, and the install could
   never commit. The seed commit is now path-scoped (scripts/brain/oobe/seed.py).
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import _brain_oobe_helpers as h

ROOT = h.REPO_ROOT
TESSCTL = ROOT / ".tess" / "bin" / "tessctl"
sys.path.insert(0, str(ROOT / "scripts" / "brain"))
from oobe import seed  # noqa: E402


def _no_site(*args: str, root: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-S", "-I", str(root / ".tess" / "bin" / "tessctl")] + list(args),
                          cwd=str(root), capture_output=True, text=True,
                          env=dict(os.environ, TESS_ROOT=str(root)), timeout=600)


def test_python_without_site_packages_really_lacks_pyyaml():
    probe = subprocess.run([sys.executable, "-S", "-I", "-c", "import yaml"], capture_output=True, text=True)
    assert probe.returncode != 0 and "No module named 'yaml'" in probe.stderr


def test_tessctl_doctor_and_verify_run_without_pyyaml():
    for verb in ("doctor", "verify"):
        done = _no_site(verb)
        assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]
        assert done.stdout.strip().splitlines()[-1].startswith("%s: OK" % verb), done.stdout[-800:]


def test_vendored_pyyaml_round_trips_the_lock_file():
    code = ("import sys; sys.path.append(%r); import yaml; d = yaml.safe_load(open(%r)); "
            "assert yaml.safe_load(yaml.safe_dump(d)) == d; print(yaml.__version__, yaml.__file__)"
            % (str(ROOT / ".tess" / "vendor"), str(ROOT / ".tess" / "tess.lock")))
    done = subprocess.run([sys.executable, "-S", "-I", "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("6.0.3 ") and "/.tess/vendor/yaml/" in done.stdout


def _tessctl_module():
    loader = importlib.machinery.SourceFileLoader("_tessctl_parity", str(TESSCTL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_seed_fallback_rules_match_the_publish_clean_gate():
    mod = _tessctl_module()
    assert seed.FALLBACK_PRIVATE_GLOBS == list(mod._PUBLISH_CLEAN_PRIVATE_GLOBS)
    assert seed.FALLBACK_ALLOWLIST == frozenset(mod._PUBLISH_CLEAN_ALLOWLIST)
    samples = ["operator/profile.json", ".env", ".env.local", "kb/raw/a.md", "clients/acme/x.md",
               "clients/_template/CLAUDE.md", "a/b/c.local.md", "x.local.md", "brain/k.age",
               ".claude/vault/vault.age", "missions/m1/mission.md", "brain/brain.json",
               "conductor/doctrine.md", ".env.example", ".tess/state/memory/x.json", "UPGRADE-NOTES.md"]
    for path in samples:
        for glob in seed.FALLBACK_PRIVATE_GLOBS:
            assert seed._fallback_match(path, [glob]) == mod.path_matches_globs(path, [glob]), (path, glob)


def test_first_commit_succeeds_without_gitignore_and_keeps_private_files_out(tmp_path):
    root = h.full_instance(tmp_path)
    for ignore in root.rglob(".gitignore"):  # what an npm-packed template used to deliver
        ignore.unlink()
    (root / ".env").write_text("PLACEHOLDER=not-a-secret\n")
    (root / "clients" / "acme").mkdir(parents=True)
    (root / "clients" / "acme" / "notes.md").write_text("client data\n")
    init = h.onboard(root, "init", "--non-interactive", "--mode", "agency", "--operator", "Probe")
    assert init.returncode == 0, init.stdout + init.stderr
    applied = h.onboard(root, "apply")
    assert applied.returncode == 0, applied.stdout[-2000:] + applied.stderr[-2000:]
    assert "left" in applied.stdout and "private file(s) out of the first commit" in applied.stdout
    log = h.git(root, "log", "--format=%s").stdout
    assert "tess: seed instance + second brain (onboarding)" in log
    tracked = set(h.git(root, "ls-files").stdout.splitlines())
    assert {"brain/brain.json", "conductor/doctrine.md", ".tess/bin/tessctl"} <= tracked
    assert not tracked & {"operator/profile.json", ".env", "clients/acme/notes.md"}
    assert "operator/user-profile.md" in tracked  # allowlisted framework stub still ships
