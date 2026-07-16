"""Static safety checks for the inert custom-roster reference kit.

The kit is intentionally documentation-only. These checks never import the
engine or execute a provider adapter: they verify that the reference files keep
their narrow schema and remain outside the curated-roster loading surface.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
KIT_RELATIVE_PATH = Path("examples/custom-roster")
MARKDOWN_TEMPLATE_NAMES = (
    "README.md",
    "identity.template.md",
    "personality.template.md",
    "soul.template.md",
)
PERSONA_TEMPLATE_NAMES = (
    "identity.template.md",
    "personality.template.md",
    "soul.template.md",
)
JSON_TEMPLATE_NAME = "squad.template.json"
REQUIRED_NAMES = frozenset((*MARKDOWN_TEMPLATE_NAMES, JSON_TEMPLATE_NAME))

# These are the current production files that define, map, or load a curated
# roster. The reference kit must never become an input to any of them.
LIVE_ROSTER_SOURCE_PATHS = (
    Path(".tess/bin/tessctl"),
    Path(".tess/core/roster-paths.json"),
    Path(".tess/tess.lock"),
    Path("tess.manifest.json"),
    Path("create-tess/src/roster.js"),
)

FORBIDDEN_JSON_FIELDS = frozenset(
    {
        "activate",
        "activation",
        "approval_authority",
        "authority",
        "bootstrap",
        "credential",
        "credentials",
        "loader",
        "live_path",
        "register",
        "registration",
        "registry",
        "secret",
        "secrets",
        "signoff",
        "verdict",
        "verifier_key",
    }
)

FORBIDDEN_MARKDOWN_PATTERNS = (
    re.compile(r"\b(?:grant|assign|give|exercise)\s+(?:[\w-]+\s+){0,2}authority\b", re.I),
    re.compile(r"\b(?:store|handle|expose|use)\s+(?:[\w-]+\s+){0,2}(?:secret|credential|token)s?\b", re.I),
    re.compile(r"\b(?:issue|sign)\s+(?:[\w-]+\s+){0,2}(?:verdict|approval)s?\b", re.I),
    re.compile(r"\bbootstrap\b", re.I),
    re.compile(r"\b(?:register|registration|activate|activation)\b", re.I),
)


def _kit_directory(root: Path) -> Path:
    return root / KIT_RELATIVE_PATH


def _read_utf8_file(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise AssertionError(f"reference-kit file must be a regular file: {path}")
    return path.read_text(encoding="utf-8")


def _validate_markdown_template(path: Path, *, requires_placeholders: bool) -> None:
    content = _read_utf8_file(path)
    if not content.startswith("# "):
        raise AssertionError(f"reference-kit Markdown needs a title: {path.name}")
    if requires_placeholders and ("<" not in content or ">" not in content):
        raise AssertionError(f"reference-kit Markdown needs visible placeholders: {path.name}")
    for pattern in FORBIDDEN_MARKDOWN_PATTERNS:
        if pattern.search(content):
            raise AssertionError(
                f"reference-kit Markdown contains an operational instruction "
                f"({pattern.pattern!r}): {path.name}"
            )


def _assert_no_forbidden_json_fields(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in FORBIDDEN_JSON_FIELDS:
                raise AssertionError(f"reference-kit JSON contains forbidden field: {key}")
            _assert_no_forbidden_json_fields(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_json_fields(child)


def _validate_json_template(path: Path) -> None:
    content = _read_utf8_file(path)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise AssertionError(f"reference-kit JSON is invalid: {error}") from error

    _assert_no_forbidden_json_fields(payload)
    if set(payload) != {"schema_version", "reference_only", "squad"}:
        raise AssertionError("reference-kit JSON has an unexpected top-level schema")
    if payload["schema_version"] != "tess-os.custom-roster.reference/v1":
        raise AssertionError("reference-kit JSON must declare the reference schema")
    if payload["reference_only"] is not True:
        raise AssertionError("reference-kit JSON must remain explicitly reference-only")

    squad = payload["squad"]
    if not isinstance(squad, dict) or set(squad) != {"name", "purpose", "members"}:
        raise AssertionError("reference-kit JSON has an unexpected squad schema")
    if not all(isinstance(squad[field], str) and squad[field] for field in ("name", "purpose")):
        raise AssertionError("reference-kit squad name and purpose must be non-empty strings")
    members = squad["members"]
    if not isinstance(members, list) or not members:
        raise AssertionError("reference-kit squad must include one reference member")

    expected_templates = {
        "identity": "identity.template.md",
        "personality": "personality.template.md",
        "soul": "soul.template.md",
    }
    for member in members:
        if not isinstance(member, dict) or set(member) != {"id", "role", "templates"}:
            raise AssertionError("reference-kit member has an unexpected schema")
        if not all(isinstance(member[field], str) and member[field] for field in ("id", "role")):
            raise AssertionError("reference-kit member id and role must be non-empty strings")
        if member["templates"] != expected_templates:
            raise AssertionError("reference-kit member must point only to local template files")


def _assert_no_live_roster_reference(root: Path) -> None:
    marker = KIT_RELATIVE_PATH.as_posix()
    for relative_path in LIVE_ROSTER_SOURCE_PATHS:
        source_path = root / relative_path
        content = _read_utf8_file(source_path)
        if marker in content:
            raise AssertionError(
                f"live roster source must not reference the reference kit: {relative_path}"
            )


def validate_reference_kit(root: Path) -> None:
    kit = _kit_directory(root)
    if not kit.is_dir() or kit.is_symlink():
        raise AssertionError("custom-roster reference kit must be a regular directory")
    found_names = frozenset(path.name for path in kit.iterdir())
    if found_names != REQUIRED_NAMES:
        raise AssertionError(
            f"custom-roster reference kit has an unexpected file set: {sorted(found_names)!r}"
        )
    for name in MARKDOWN_TEMPLATE_NAMES:
        _validate_markdown_template(
            kit / name,
            requires_placeholders=name in PERSONA_TEMPLATE_NAMES,
        )
    _validate_json_template(kit / JSON_TEMPLATE_NAME)
    _assert_no_live_roster_reference(root)


class CustomRosterReferenceKitTests(unittest.TestCase):
    def test_checked_in_reference_kit_is_inert_and_well_formed(self) -> None:
        validate_reference_kit(REPOSITORY_ROOT)

    def test_live_roster_reference_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            source_path = temporary_root / ".tess/bin/tessctl"
            source_path.parent.mkdir(parents=True)
            source_path.write_text(
                "config = 'examples/custom-roster/squad.template.json'\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AssertionError, "must not reference"):
                _assert_no_live_roster_reference(
                    _source_root_with_only(temporary_root, source_path)
                )

    def test_operational_markdown_mutations_are_rejected(self) -> None:
        mutations = (
            "Grant approval authority to this persona.",
            "Handle production secrets for this squad.",
            "Issue a signed verdict after each task.",
            "Bootstrap the custom roster during startup.",
            "Register this persona with the live host.",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary_directory:
                temporary_root = _copy_kit_into(Path(temporary_directory))
                target = _kit_directory(temporary_root) / "identity.template.md"
                target.write_text(
                    target.read_text(encoding="utf-8") + "\n" + mutation + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(AssertionError, "operational instruction"):
                    validate_reference_kit(temporary_root)

    def test_operational_json_field_mutations_are_rejected(self) -> None:
        for field_name in sorted(FORBIDDEN_JSON_FIELDS):
            with self.subTest(field_name=field_name), tempfile.TemporaryDirectory() as temporary_directory:
                temporary_root = _copy_kit_into(Path(temporary_directory))
                target = _kit_directory(temporary_root) / JSON_TEMPLATE_NAME
                payload = json.loads(target.read_text(encoding="utf-8"))
                payload[field_name] = "must-not-be-a-reference-field"
                target.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(AssertionError, "forbidden field"):
                    validate_reference_kit(temporary_root)


def _copy_kit_into(temporary_root: Path) -> Path:
    source = _kit_directory(REPOSITORY_ROOT)
    destination = _kit_directory(temporary_root)
    destination.parent.mkdir(parents=True)
    shutil.copytree(source, destination)
    for relative_path in LIVE_ROSTER_SOURCE_PATHS:
        target = temporary_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# no custom roster reference here\n", encoding="utf-8")
    return temporary_root


def _source_root_with_only(temporary_root: Path, source_path: Path) -> Path:
    for relative_path in LIVE_ROSTER_SOURCE_PATHS:
        target = temporary_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target != source_path:
            target.write_text("# no custom roster reference here\n", encoding="utf-8")
    return temporary_root


if __name__ == "__main__":
    unittest.main()
