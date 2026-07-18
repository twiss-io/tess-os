"""Independent checks for the advisory, read-only manifest validator."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pytest

from conftest import REPO_ROOT
from tools import adapter_manifest_validator as validator
from tools.validate_adapter_manifests import main as cli_main


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())


def _fixture_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for relative in (
        Path("adapters/contracts/adapter-manifest.schema.json"),
        Path(".tess/bin/tessctl"),
    ):
        _copy_file(REPO_ROOT / relative, root / relative)
    for manifest in validator.MANIFEST_NAMES:
        _copy_file(
            REPO_ROOT / validator.MANIFEST_DIRECTORY / manifest,
            root / validator.MANIFEST_DIRECTORY / manifest,
        )
    for relative in (
        Path("adapters/claude-code/README.md"),
        Path("adapters/codex/README.md"),
        Path("adapters/generic/README.md"),
        Path("docs/STATUS.md"),
    ):
        _copy_file(REPO_ROOT / relative, root / relative)
    return root


def _read_manifest(root: Path, name: str) -> Dict[str, object]:
    path = root / validator.MANIFEST_DIRECTORY / name
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(root: Path, name: str, data: Dict[str, object]) -> None:
    path = root / validator.MANIFEST_DIRECTORY / name
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _tree_bytes(root: Path) -> List[Tuple[str, bytes]]:
    return [
        (str(path.relative_to(root)), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    ]


def test_real_checkout_is_valid_and_the_validator_is_advisory_only():
    assert validator.validate_repository(REPO_ROOT) == []
    assert set(validator.MANIFEST_NAMES) == {
        "claude-code.adapter-manifest.json",
        "codex.adapter-manifest.json",
        "generic.adapter-manifest.json",
        "perplexity.adapter-manifest.json",
    }


def test_cli_and_api_have_deterministic_advisory_parity(tmp_path, capsys):
    root = _fixture_repository(tmp_path)
    expected = validator.validate_repository(root)
    assert expected == []

    assert cli_main(["--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"advisory": True, "findings": expected, "valid": True}

    data = _read_manifest(root, "codex.adapter-manifest.json")
    data["support_level"] = "C4"
    _write_manifest(root, "codex.adapter-manifest.json", data)
    expected = validator.validate_repository(root)
    assert expected == sorted(expected)
    assert cli_main(["--root", str(root), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"advisory": True, "findings": expected, "valid": False}


def test_root_anchor_is_a_normal_advisory_failure_not_a_descriptor_crash(tmp_path):
    findings = validator.validate_repository(Path(tmp_path.anchor))
    assert isinstance(findings, list)
    assert findings


def test_valid_run_is_read_only_and_does_not_need_network_or_subprocess(tmp_path, monkeypatch):
    root = _fixture_repository(tmp_path)
    before = _tree_bytes(root)

    def forbidden(*args, **kwargs):
        pytest.fail("validator attempted a filesystem mutation")

    for method in ("write_bytes", "write_text", "mkdir", "unlink", "rename", "replace", "chmod"):
        monkeypatch.setattr(Path, method, forbidden)
    assert validator.validate_repository(root) == []
    assert _tree_bytes(root) == before

    validator_source = Path(validator.__file__).read_text(encoding="utf-8")
    tree = ast.parse(validator_source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    )
    assert not {"socket", "subprocess", "urllib", "http", "requests"} & imported
    os_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
    }
    assert os_calls <= {"open", "dup", "fstat", "read", "close", "listdir"}


def test_strict_json_rejects_duplicate_root_and_nested_keys(tmp_path):
    root = _fixture_repository(tmp_path)
    path = root / validator.MANIFEST_DIRECTORY / "codex.adapter-manifest.json"
    path.write_text(
        '{"schema_version":"tess.adapter-manifest.v1",'
        '"adapter_id":"codex","adapter_id":"codex"}',
        encoding="utf-8",
    )
    findings = validator.validate_repository(root)
    assert any("duplicate object key 'adapter_id'" in finding for finding in findings)

    root = _fixture_repository(tmp_path / "nested")
    path = root / validator.MANIFEST_DIRECTORY / "codex.adapter-manifest.json"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace('"kind": "repository-source",', '"kind": "repository-source", "kind": "status-page",', 1),
        encoding="utf-8",
    )
    findings = validator.validate_repository(root)
    assert any("duplicate object key 'kind'" in finding for finding in findings)


def test_rejects_c4_authority_and_capability_claims(tmp_path):
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "codex.adapter-manifest.json")
    data["support_level"] = "C4"
    data["authority"] = "self-issued"
    data["capabilities"] = ["approval"]
    _write_manifest(root, "codex.adapter-manifest.json", data)

    findings = validator.validate_repository(root)
    assert any("C4" in finding for finding in findings)
    assert any("authority-bearing field 'authority'" in finding for finding in findings)
    assert any("authority-bearing capability 'approval'" in finding for finding in findings)


def test_rejects_missing_and_unknown_manifest_inputs(tmp_path):
    root = _fixture_repository(tmp_path)
    (root / validator.MANIFEST_DIRECTORY / "generic.adapter-manifest.json").unlink()
    (root / validator.MANIFEST_DIRECTORY / "unreviewed.adapter-manifest.json").write_text("{}", encoding="utf-8")
    findings = validator.validate_repository(root)
    assert any("missing canonical manifest 'generic.adapter-manifest.json'" in finding for finding in findings)
    assert any("unexpected manifest input 'unreviewed.adapter-manifest.json'" in finding for finding in findings)


def test_rejects_symlink_or_nonregular_schema_manifest_and_evidence(tmp_path):
    actual_root = _fixture_repository(tmp_path / "root-link")
    root_link = tmp_path / "linked-root"
    root_link.symlink_to(actual_root, target_is_directory=True)
    findings = validator.validate_repository(root_link)
    assert any("root: repository root must not be a symlink" in finding for finding in findings)

    root = _fixture_repository(tmp_path)
    schema = root / validator.SCHEMA_PATH
    target = root / "schema-target.json"
    target.write_bytes(schema.read_bytes())
    schema.unlink()
    schema.symlink_to(target)
    findings = validator.validate_repository(root)
    assert any("adapter-manifest.schema.json: symlinks are not allowed" in finding for finding in findings)

    root = _fixture_repository(tmp_path / "manifest")
    manifest = root / validator.MANIFEST_DIRECTORY / "generic.adapter-manifest.json"
    copied = root / "copied-manifest.json"
    copied.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(copied)
    findings = validator.validate_repository(root)
    assert any("generic.adapter-manifest.json: symlinks are not allowed" in finding for finding in findings)

    root = _fixture_repository(tmp_path / "evidence")
    data = _read_manifest(root, "codex.adapter-manifest.json")
    evidence = data["evidence"]
    assert isinstance(evidence, list)
    evidence[0]["path"] = "evidence-link.md"
    _write_manifest(root, "codex.adapter-manifest.json", data)
    (root / "evidence-link.md").symlink_to(root / "docs/STATUS.md")
    findings = validator.validate_repository(root)
    assert any("evidence[0].path: symlinks are not allowed" in finding for finding in findings)

    root = _fixture_repository(tmp_path / "nonregular")
    manifest = root / validator.MANIFEST_DIRECTORY / "generic.adapter-manifest.json"
    manifest.unlink()
    manifest.mkdir()
    findings = validator.validate_repository(root)
    assert any("generic.adapter-manifest.json: must be an existing regular file" in finding for finding in findings)

    root = _fixture_repository(tmp_path / "evidence-directory")
    data = _read_manifest(root, "codex.adapter-manifest.json")
    evidence = data["evidence"]
    assert isinstance(evidence, list)
    evidence[0]["path"] = "evidence-directory"
    _write_manifest(root, "codex.adapter-manifest.json", data)
    (root / "evidence-directory").mkdir()
    findings = validator.validate_repository(root)
    assert any("evidence[0].path: must be an existing regular file" in finding for finding in findings)

    root = _fixture_repository(tmp_path / "source-link")
    source = root / validator.ENGINE_PATH
    target = root / "tessctl-source"
    target.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(target)
    findings = validator.validate_repository(root)
    assert any(".tess/bin/tessctl: symlinks are not allowed" in finding for finding in findings)


def test_rejects_path_traversal_absolute_windows_and_source_parity_drift(tmp_path):
    root = _fixture_repository(tmp_path)
    data = _read_manifest(root, "codex.adapter-manifest.json")
    evidence = data["evidence"]
    assert isinstance(evidence, list)
    evidence[0]["path"] = "../outside.md"
    evidence[1]["path"] = "/outside.md"
    evidence.append({"kind": "status-page", "path": r"C:\\outside.md", "note": "invalid"})
    _write_manifest(root, "codex.adapter-manifest.json", data)
    findings = validator.validate_repository(root)
    assert sum("traversal-free repository-relative path" in finding for finding in findings) >= 3

    root = _fixture_repository(tmp_path / "parity")
    engine = root / validator.ENGINE_PATH
    source = engine.read_text(encoding="utf-8")
    engine.write_text(source.replace('"codex": CodexExecDriver,', '"other": CodexExecDriver,'), encoding="utf-8")
    findings = validator.validate_repository(root)
    assert any("expected local process driver 'codex' is absent" in finding for finding in findings)


def test_source_parity_rejects_dynamic_or_malformed_registry_source(tmp_path):
    root = _fixture_repository(tmp_path)
    engine = root / validator.ENGINE_PATH
    source = engine.read_text(encoding="utf-8")
    engine.write_text(source.replace("RENDER_TARGETS: dict = {", "RENDER_TARGETS: dict = build_targets()", 1), encoding="utf-8")
    findings = validator.validate_repository(root)
    # Replacing only the declaration deliberately leaves the former literal's
    # body behind.  Some supported tokenizers reject that malformed source
    # before reaching the direct-assignment check; both paths must fail closed
    # through the same advisory source-parity boundary.
    assert any("AST-only source parity failed" in finding for finding in findings)

    root = _fixture_repository(tmp_path / "malformed")
    engine = root / validator.ENGINE_PATH
    engine.write_text(engine.read_text(encoding="utf-8") + "\n\"\"\"unterminated", encoding="utf-8")
    findings = validator.validate_repository(root)
    assert any("AST-only source parity failed" in finding for finding in findings)


def test_source_parity_rejects_unmanifested_targets_and_registry_mutation(tmp_path):
    root = _fixture_repository(tmp_path)
    engine = root / validator.ENGINE_PATH
    source = engine.read_text(encoding="utf-8")
    engine.write_text(
        source.replace(
            '"generic": GenericRenderTarget(),',
            '"generic": GenericRenderTarget(),\n    "unmanifested": GenericRenderTarget(),',
            1,
        ),
        encoding="utf-8",
    )
    findings = validator.validate_repository(root)
    assert any("render target 'unmanifested' has no canonical manifest-backed claim" in finding for finding in findings)

    mutations = (
        ("\nif True:\n    RENDER_TARGETS = build_targets()\n", "RENDER_TARGETS: source rebinds the registry"),
        ("\nRENDER_TARGETS.update({})\n", "RENDER_TARGETS: source uses unapproved registry method .update"),
        ("\nRUN_DRIVERS['new'] = object()\n", "RUN_DRIVERS: source mutates a registry entry"),
        ("\nRENDER_TARGETS.__setitem__('new', object())\n", "RENDER_TARGETS: source uses unapproved registry method .__setitem__"),
        ("\ndict.update(RENDER_TARGETS, {'new': object()})\n", "RENDER_TARGETS: source uses the registry outside approved read-only forms"),
    )
    for index, (snippet, expected) in enumerate(mutations):
        mutation_root = _fixture_repository(tmp_path / "mutation-{}".format(index))
        mutation_engine = mutation_root / validator.ENGINE_PATH
        mutation_engine.write_text(mutation_engine.read_text(encoding="utf-8") + snippet, encoding="utf-8")
        findings = validator.validate_repository(mutation_root)
        assert any(expected in finding for finding in findings), findings


def test_source_parity_allows_only_exact_renderer_registry_reads(tmp_path):
    root = _fixture_repository(tmp_path)
    assert validator.validate_repository(root) == []

    rejected_uses = (
        ("\nregistry_alias = RENDER_TARGETS\n", "outside approved read-only forms"),
        ("\ntuple(RENDER_TARGETS)\n", "outside approved read-only forms"),
        ("\nregistry_set(RENDER_TARGETS)\n", "outside approved read-only forms"),
        ("\nnamespace.set(RENDER_TARGETS)\n", "outside approved read-only forms"),
        ("\nset(RENDER_TARGETS)\n", "outside approved read-only forms"),
        ("\nset(RENDER_TARGETS, object())\n", "outside approved read-only forms"),
    )
    for index, (snippet, expected) in enumerate(rejected_uses):
        rejected_root = _fixture_repository(tmp_path / "rejected-read-{}".format(index))
        engine = rejected_root / validator.ENGINE_PATH
        engine.write_text(engine.read_text(encoding="utf-8") + snippet, encoding="utf-8")
        findings = validator.validate_repository(rejected_root)
        assert any(expected in finding for finding in findings), findings

    literal_root = _fixture_repository(tmp_path / "unauthorized-literal")
    engine = literal_root / validator.ENGINE_PATH
    source = engine.read_text(encoding="utf-8")
    source = source.replace(
        "def _gate_renderer_registry_targets(blob: bytes, label: str)",
        "def unauthorized_renderer_reader():\n"
        "    return object().id == \"RENDER_TARGETS\"\n\n\n"
        "def _gate_renderer_registry_targets(blob: bytes, label: str)",
        1,
    )
    engine.write_text(source, encoding="utf-8")
    findings = validator.validate_repository(literal_root)
    assert any("direct registry literal outside canonical declaration" in finding for finding in findings)

    helper_misuse_root = _fixture_repository(tmp_path / "helper-literal-misuse")
    engine = helper_misuse_root / validator.ENGINE_PATH
    source = engine.read_text(encoding="utf-8")
    source = source.replace(
        "    try:\n        module = ast.parse(blob.decode(\"utf-8\"), filename=label)",
        "    consume(\"RENDER_TARGETS\")\n"
        "    try:\n        module = ast.parse(blob.decode(\"utf-8\"), filename=label)",
        1,
    )
    engine.write_text(source, encoding="utf-8")
    findings = validator.validate_repository(helper_misuse_root)
    assert any("direct registry literal outside canonical declaration" in finding for finding in findings)


def test_source_parity_rejects_dynamic_registry_reflection(tmp_path):
    reflections = (
        (
            '\nglobals()["RENDER_TARGETS"]["unmanifested"] = GenericRenderTarget()\n',
            "source uses dynamic reflection globals()",
        ),
        (
            '\nvars()["RUN_DRIVERS"]["unmanifested"] = object()\n',
            "source uses dynamic reflection vars()",
        ),
        (
            '\nlocals()["RENDER_TARGETS"]["unmanifested"] = GenericRenderTarget()\n',
            "source uses dynamic reflection locals()",
        ),
        ('\ngetattr(module, "RENDER_TARGETS")\n', "source reflection getattr() names registry 'RENDER_TARGETS'"),
        ('\nsetattr(module, "RUN_DRIVERS", {})\n', "source reflection setattr() names registry 'RUN_DRIVERS'"),
        ('\neval("RENDER_TARGETS")\n', "source uses dynamic reflection eval()"),
        ('\nexec("RUN_DRIVERS = {}")\n', "source uses dynamic reflection exec()"),
        ('\n__builtins__["globals"]()["RENDER_TARGETS"] = {}\n', "source uses dynamic reflection __builtins__()"),
        ('\nsys.modules[__name__].__dict__["RENDER_TARGETS"] = {}\n', "source uses dynamic reflection __dict__()"),
        ("\ngetattr(args, dynamic_field)\n", "source getattr() has ambiguous dynamic provenance"),
    )
    for index, (snippet, expected) in enumerate(reflections):
        root = _fixture_repository(tmp_path / "reflection-{}".format(index))
        engine = root / validator.ENGINE_PATH
        engine.write_text(engine.read_text(encoding="utf-8") + snippet, encoding="utf-8")
        findings = validator.validate_repository(root)
        assert any(expected in finding for finding in findings), findings

    root = _fixture_repository(tmp_path / "literal-tripwire")
    engine = root / validator.ENGINE_PATH
    engine.write_text(engine.read_text(encoding="utf-8") + '\nregistry_name = "RUN_DRIVERS"\n', encoding="utf-8")
    findings = validator.validate_repository(root)
    assert any("RUN_DRIVERS: source contains direct registry literal outside canonical declaration" in finding for finding in findings)


def test_no_follow_descriptor_rejects_a_manifest_swapped_to_symlink(tmp_path, monkeypatch):
    root = _fixture_repository(tmp_path)
    manifest = root / validator.MANIFEST_DIRECTORY / "codex.adapter-manifest.json"
    outside = root / "outside-manifest.json"
    outside.write_bytes(manifest.read_bytes())
    real_open = validator.os.open
    swapped = {"done": False}

    def swap_before_open(path, flags, mode=0o777, *, dir_fd=None):
        if path == "codex.adapter-manifest.json" and dir_fd is not None and not swapped["done"]:
            manifest.unlink()
            manifest.symlink_to(outside)
            swapped["done"] = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(validator.os, "open", swap_before_open)
    findings = validator.validate_repository(root)
    assert swapped["done"]
    assert any("adapters/manifests/codex.adapter-manifest.json: symlinks are not allowed" in finding for finding in findings)


def test_manifest_enumeration_keeps_the_open_directory_descriptor(tmp_path, monkeypatch):
    root = _fixture_repository(tmp_path)
    manifest_directory = root / validator.MANIFEST_DIRECTORY
    replaced_directory = root / "original-manifests"
    outside = root / "outside-manifest.json"
    outside.write_text("{}", encoding="utf-8")
    real_listdir = validator.os.listdir
    swapped = {"done": False}

    def swap_after_listing(descriptor):
        names = real_listdir(descriptor)
        if not swapped["done"]:
            manifest_directory.rename(replaced_directory)
            manifest_directory.mkdir()
            (manifest_directory / "codex.adapter-manifest.json").symlink_to(outside)
            swapped["done"] = True
        return names

    monkeypatch.setattr(validator.os, "listdir", swap_after_listing)
    assert validator.validate_repository(root) == []
    assert swapped["done"]


def test_source_registry_parity_ignores_unrelated_newer_annotation_syntax(tmp_path):
    root = _fixture_repository(tmp_path)
    engine = root / validator.ENGINE_PATH
    engine.write_text(
        engine.read_text(encoding="utf-8")
        + "\nunrelated_python_310_annotation: object = bytes | None\n"
        + "match unrelated_subject:\n    case _:\n        pass\n",
        encoding="utf-8",
    )
    assert validator.validate_repository(root) == []


def test_source_parity_ast_parses_only_extracted_dictionary_fragments(tmp_path, monkeypatch):
    root = _fixture_repository(tmp_path)
    parsed = []
    original_parse = validator.ast.parse

    def record_parse(source, *args, **kwargs):
        parsed.append(source)
        return original_parse(source, *args, **kwargs)

    monkeypatch.setattr(validator.ast, "parse", record_parse)
    assert validator.validate_repository(root) == []
    assert len(parsed) == 2
    assert all(isinstance(fragment, str) and fragment.lstrip().startswith("{") for fragment in parsed)
    assert all("def cmd_" not in fragment for fragment in parsed)
