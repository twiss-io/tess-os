"""v1.0.1 (2026-09-29 Codex review, HIGH): the vendored PyYAML at
.tess/vendor/yaml must never run unless every file matches the sha256 table
embedded in .tess/bin/tessctl.

Before the fix the engine appended .tess/vendor to sys.path and imported
whatever was there, so an edited `yaml/__init__.py`, a planted stale `.pyc`
or a top-level `.tess/vendor/_yaml.py` ran on doctor/gate/update before any
signature check. Each test below plants one of those and asserts a sentinel
file is never created.

The engine is run with `-I -B -S`: -S drops site-packages, so an installed
PyYAML cannot hide the fallback path these tests exercise.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
ENGINE = REPO / ".tess" / "bin" / "tessctl"
VENDOR = REPO / ".tess" / "vendor"


def _embedded_table() -> dict:
    text = ENGINE.read_text(encoding="utf-8")
    block = text.split("_VENDORED_YAML_SHA256 = {", 1)[1].split("}", 1)[0]
    return dict(re.findall(r'"([^"]+\.py)": "([0-9a-f]{64})"', block))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A throwaway root holding only the engine and the vendored PyYAML."""
    (tmp_path / ".tess" / "bin").mkdir(parents=True)
    shutil.copy2(ENGINE, tmp_path / ".tess" / "bin" / "tessctl")
    shutil.copytree(VENDOR, tmp_path / ".tess" / "vendor",
                    ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


def _run(root: Path, *args: str):
    return subprocess.run([sys.executable, "-I", "-B", "-S", str(root / ".tess/bin/tessctl"), *args],
                          cwd=str(root), capture_output=True, text=True,
                          env={**os.environ, "TESS_ROOT": str(root)})


def _sentinel_code(path: Path) -> str:
    return f"open({str(path)!r}, 'w').close()\n"


def test_pyyaml_is_not_importable_without_site_packages():
    r = subprocess.run([sys.executable, "-I", "-S", "-c", "import yaml"], capture_output=True)
    assert r.returncode != 0, "this interpreter ships PyYAML in the stdlib path; tests would be vacuous"


def test_embedded_table_covers_every_vendored_module_and_matches_it():
    table = _embedded_table()
    shipped = {p.name for p in (VENDOR / "yaml").glob("*.py")}
    assert set(table) == shipped
    for name, want in table.items():
        assert hashlib.sha256((VENDOR / "yaml" / name).read_bytes()).hexdigest() == want, name


def test_pristine_vendored_yaml_loads_and_writes_no_bytecode(root: Path):
    r = _run(root, "--help")
    assert r.returncode == 0, r.stderr
    assert not (root / ".tess/vendor/yaml/__pycache__").exists()


def test_edited_vendored_module_is_refused_before_it_runs(root: Path, tmp_path: Path):
    sentinel = tmp_path / "SENTINEL_edit"
    with open(root / ".tess/vendor/yaml/__init__.py", "a", encoding="utf-8") as fh:
        fh.write(_sentinel_code(sentinel))
    r = _run(root, "--help")
    assert r.returncode != 0
    assert "does not match this Tess OS release" in r.stderr and "__init__.py" in r.stderr
    assert not sentinel.exists()


def test_extra_module_in_the_package_is_refused(root: Path, tmp_path: Path):
    sentinel = tmp_path / "SENTINEL_extra"
    (root / ".tess/vendor/yaml/_yaml.py").write_text(_sentinel_code(sentinel))  # cyaml.py imports yaml._yaml
    r = _run(root, "--help")
    assert r.returncode != 0 and "_yaml.py is not part of the bundled PyYAML" in r.stderr
    assert not sentinel.exists()


def test_planted_stale_pyc_is_never_loaded(root: Path, tmp_path: Path):
    """A __pycache__ .pyc whose header matches the real source's mtime and
    size is what CPython would load instead of the verified source."""
    sentinel = tmp_path / "SENTINEL_pyc"
    src = root / ".tess/vendor/yaml/__init__.py"
    code = compile(_sentinel_code(sentinel) + src.read_text(encoding="utf-8"), str(src), "exec")
    st = src.stat()
    from importlib._bootstrap_external import _code_to_timestamp_pyc  # stdlib, stable since 3.7
    pyc = Path(importlib.util.cache_from_source(str(src)))
    pyc.parent.mkdir(exist_ok=True)
    pyc.write_bytes(bytes(_code_to_timestamp_pyc(code, int(st.st_mtime), st.st_size)))
    r = _run(root, "--help")
    assert r.returncode == 0, r.stderr
    assert not sentinel.exists()


def test_vendor_dir_is_not_on_sys_path(root: Path):
    """The old fallback appended .tess/vendor to sys.path, so any module name
    the engine imported later and the stdlib lacked resolved there. Now the
    verified finder serves yaml alone and .tess/vendor never joins sys.path."""
    probe = ("import runpy, sys\n"
             f"runpy.run_path({str(root / '.tess/bin/tessctl')!r})\n"
             "print([p for p in sys.path if p.rstrip('/').endswith('vendor')])\n"
             "print(type(sys.modules['yaml'].__spec__.loader).__name__)\n")
    r = subprocess.run([sys.executable, "-I", "-B", "-S", "-c", probe], cwd=str(root),
                       capture_output=True, text=True, env={**os.environ, "TESS_ROOT": str(root)})
    assert r.returncode == 0, r.stderr
    assert r.stdout.split("\n")[:2] == ["[]", "_VerifiedYamlFinder"], r.stdout


def test_vendor_tree_is_security_tier_and_pinned_by_the_lock():
    for rel in ("core/policy/policy.yaml", ".tess/core/policy/policy.yaml"):
        rules = yaml.safe_load((REPO / rel).read_text())["policy"]["rules"]
        rule = next(r for r in rules if r["id"] == "tess-os-security-tier-doctrine")
        assert ".tess/vendor/**" in rule["globs"], rel
    files = yaml.safe_load((REPO / ".tess/tess.lock").read_text())["files"]
    vendored = sorted(p.relative_to(REPO).as_posix() for p in VENDOR.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts)
    assert vendored
    for rel in vendored:
        entry = files.get(rel)
        assert entry and entry["tier"] == "security", rel
        assert entry["base_sha"] == "sha256:" + hashlib.sha256((REPO / rel).read_bytes()).hexdigest(), rel
