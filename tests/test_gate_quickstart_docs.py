import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
QUICKSTART_PATH = REPO_ROOT / "docs" / "GATE_QUICKSTART.md"


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
        "./tessctl doctor\n./tessctl verify\n./tessctl gate ci",
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
