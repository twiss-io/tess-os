import hashlib
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
QUICKSTART_PATH = REPO_ROOT / "docs" / "GATE_QUICKSTART.md"
README_PATH = REPO_ROOT / "README.md"
SIGNING_GUIDE_PATH = REPO_ROOT / "conductor" / "verdict-signing.md"
SIGNING_GUIDE_MIRROR_PATH = REPO_ROOT / ".tess" / "core" / "conductor" / "verdict-signing.md"
LOCK_PATH = REPO_ROOT / ".tess" / "tess.lock"
GENERIC_ADAPTER_PATH = REPO_ROOT / "adapters" / "generic" / "README.md"
WIZARD_SOURCE_PATH = REPO_ROOT / "create-tess" / "src" / "index.js"


def test_gate_quickstart_documents_custody_boundary_without_bootstrap_commands():
    document = QUICKSTART_PATH.read_text(encoding="utf-8")

    for required_text in (
        "Technology-preview boundary",
        "first-key design and GitHub required-check enforcement are still unresolved",
        "no covering APPROVE verdict found",
        "generate a key;",
        "register a public key in policy;",
        "write or sign a verdict or sign-off;",
        "candidate repository must never create the trust anchor",
        "There is no self-service bootstrap path documented here.",
    ):
        assert required_text in document

    bash_blocks = re.findall(r"```bash\n(.*?)\n```", document, flags=re.DOTALL)
    assert bash_blocks == [
        "./tessctl doctor\n./tessctl verify\n./tessctl gate ci --base <BASE_REF> --head <HEAD_REF>",
        "./tessctl verdict verify path/to/existing.verdict.yaml",
    ]

    executable_text = "\n".join(bash_blocks)
    for forbidden_command in (
        "verdict keygen",
        "verdict sign",
        "signoff sign",
        "gpg --gen-key",
        "gpg --full-gen-key",
        "gpg --export",
        "git push --no-verify",
        "git push --force",
        "tessctl lock --regen",
    ):
        assert forbidden_command not in executable_text


def test_safe_gate_ci_examples_supply_required_refs():
    expected = "./tessctl gate ci --base <BASE_REF> --head <HEAD_REF>"

    for path in (README_PATH, QUICKSTART_PATH):
        document = path.read_text(encoding="utf-8")
        assert re.search(r"use two existing\s+immutable\s+refs", document)
        assert expected in document
        assert re.search(r"^\./tessctl gate ci$", document, flags=re.MULTILINE) is None


def test_managed_signing_guide_is_mirrored_and_custody_only():
    guide = SIGNING_GUIDE_PATH.read_text(encoding="utf-8")
    mirror = SIGNING_GUIDE_MIRROR_PATH.read_text(encoding="utf-8")

    assert guide == mirror
    for required_text in (
        "Technology-preview boundary",
        "empty verifier and sign-off registries",
        "There is no self-service bootstrap path",
        "candidate repository must never\ncreate or register the trust anchor",
        "Escalate to Xavier",
        "Security-governed policy, key-registry, and workflow surfaces remain outside",
        "NO-MERGE proposal and Xavier custody",
    ):
        assert required_text in guide

    for forbidden_text in (
        "tessctl verdict keygen",
        "tessctl verdict sign",
        "tessctl signoff sign",
        "gpg --export",
        "git push --no-verify",
        "workflow_dispatch",
        "grace period",
    ):
        assert forbidden_text not in guide


def test_verdict_signing_guide_lock_entry_matches_mirror():
    lock = LOCK_PATH.read_text(encoding="utf-8")
    entry = re.search(
        r"^  \.tess/core/conductor/verdict-signing\.md:\n(?P<body>(?:^    .*\n)+)",
        lock,
        flags=re.MULTILINE,
    )

    assert entry is not None
    body = entry.group("body")
    assert "    live_path: conductor/verdict-signing.md\n" in body
    digest = re.search(r"^    base_sha: sha256:([0-9a-f]{64})$", body, flags=re.MULTILINE)
    assert digest is not None
    assert digest.group(1) == hashlib.sha256(SIGNING_GUIDE_MIRROR_PATH.read_bytes()).hexdigest()


def test_wizard_source_has_custody_only_first_push_notice():
    source = WIZARD_SOURCE_PATH.read_text(encoding="utf-8")
    notice = source.split("function printFirstPushNotice()", 1)[1].split(
        "function printGateStatus", 1
    )[0]

    for required_text in (
        "Local scaffold ready; protected production work remains blocked.",
        "first governed push can fail closed",
        "Do not bypass or disable the hook",
        "escalate to Xavier",
        "Local scaffold complete; production protection requires external custody",
    ):
        assert required_text in source

    for forbidden_text in (
        "git push --no-verify",
        "onboard a real verifier",
        "tessctl verdict keygen",
    ):
        assert forbidden_text not in notice


def test_generic_adapter_does_not_claim_governance_activation():
    document = GENERIC_ADAPTER_PATH.read_text(encoding="utf-8")

    for required_text in (
        "## Governance boundary",
        "emits `AGENTS.md` and prompt mirrors only",
        "does not\nconfigure CI, branch protection, a verifier or sign-off trust root, or native\ngate enforcement",
        "Do not treat rendered files as approval or a\nbootstrap instruction",
        "../../docs/GATE_QUICKSTART.md",
    ):
        assert required_text in document

    for forbidden_claim in (
        "enables native gate enforcement",
        "configures a verifier trust root",
        "configures branch protection",
    ):
        assert forbidden_claim not in document
