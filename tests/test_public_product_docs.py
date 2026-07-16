"""Public product-language claims pinned to checked-in implementation evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import REPO_ROOT


PUBLIC_DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "PLATFORM_SUPPORT.md",
    REPO_ROOT / "docs" / "TRUST_SETUP.md",
    REPO_ROOT / "docs" / "PRODUCT_FAMILY.md",
    REPO_ROOT / "docs" / "FRAMING_MIGRATION.md",
    REPO_ROOT / "docs" / "STATUS.md",
    REPO_ROOT / "create-tess" / "README.md",
)

MANIFESTS = REPO_ROOT / "adapters" / "manifests"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json(path: Path):
    return json.loads(_read(path))


def test_root_readme_leads_with_honest_model_neutral_governance_claim():
    readme = _read(REPO_ROOT / "README.md")

    for claim in (
        "signed, fail-closed review gate",
        "model-neutral\ngovernance harness",
        "Tess OS does not improve a model's intelligence",
        "no covering APPROVE verdict found",
        "use two existing\nimmutable refs",
        "./tessctl gate ci --base <BASE_REF> --head <HEAD_REF>",
        "Current `main` is not a production admission control.",
    ):
        assert claim in readme


def test_platform_labels_match_advisory_manifest_evidence():
    support = _read(REPO_ROOT / "docs" / "PLATFORM_SUPPORT.md")
    install_manifest = _json(REPO_ROOT / "tess.manifest.json")
    expected = {
        "claude-code": ("C3", "preview", "Claude Code"),
        "codex": ("C2", "preview", "OpenAI Codex"),
        "generic": ("C2", "preview", "Generic `AGENTS.md` hosts"),
        "perplexity": ("C0", "not-supported", "Perplexity"),
    }

    for adapter_id, (level, status, public_name) in expected.items():
        record = _json(MANIFESTS / f"{adapter_id}.adapter-manifest.json")
        assert record["support_level"] == level
        assert record["status"] == status
        assert re.search(
            rf"\| {re.escape(public_name)} \| [^\n]*\({level}\)",
            support,
        )

    assert "Perplexity renderer, driver" in support
    assert "No registered target or driver exists today." in support
    assert "supports all models" in support  # Explicitly rejected, not advertised.
    assert install_manifest["render_targets"]["enabled"] == ["claude-code"]


def test_product_family_separates_current_core_from_planned_services():
    family = _read(REPO_ROOT / "docs" / "PRODUCT_FAMILY.md")

    for claim in (
        "## Tess OS — available as a technology preview",
        "## Tess Cloud — planned optional coordination",
        "## Tess Vault — planned credential capabilities",
        "Cloud must remain optional.",
        "Raw credentials must stay out of prompts",
        "current local `tessctl vault` primitive",
        "not the planned Tess Vault product",
    ):
        assert claim in family


def test_trust_setup_has_no_self_bootstrap_recipe():
    trust = _read(REPO_ROOT / "docs" / "TRUST_SETUP.md")

    for claim in (
        "contains no commands\nfor creating keys",
        "no covering APPROVE verdict found",
        "must not also create the authority",
        "must never silently create authority",
        "no safe self-service production bootstrap",
    ):
        assert claim in trust

    for forbidden_command in (
        "tessctl verdict keygen",
        "tessctl verdict sign",
        "tessctl signoff sign",
        "gpg --gen-key",
        "git push --no-verify",
        "git push --force",
    ):
        assert forbidden_command not in trust


def test_npm_metadata_describes_real_package_boundaries_without_version_bump():
    root_package = _json(REPO_ROOT / "package.json")
    wizard_package = _json(REPO_ROOT / "create-tess" / "package.json")

    assert root_package["version"] == "0.1.0"
    assert root_package["description"] == (
        "Signed, fail-closed review gate and model-neutral governance harness "
        "for coding-agent output."
    )
    assert {"ai-governance", "review-gate", "claude-code", "codex"} <= set(
        root_package["keywords"]
    )

    assert wizard_package["version"] == "0.1.1"
    assert wizard_package["description"] == (
        "Guided local setup wizard for the Tess OS governance harness, with a "
        "Claude Code default and opt-in Codex and generic targets."
    )
    assert {"ai-governance", "review-gate", "claude-code", "codex"} <= set(
        wizard_package["keywords"]
    )


def test_public_docs_do_not_make_inflated_affirmative_claims():
    text = "\n".join(_read(path) for path in PUBLIC_DOCS)

    for forbidden in (
        "Tess OS makes models better",
        "Tess OS improves models",
        "Tess improves models",
        "Tess OS supports all models",
        "Tess OS supports every model",
        "Tess OS works with every model",
        "universal model support is available",
        "Tess OS is production-ready",
        "Tess OS is production certified",
        "Tess Cloud is available today",
        "Tess Cloud is live",
        "Tess Cloud is shipped",
        "Tess Vault is available today",
        "Tess Vault is live",
        "Tess Vault is shipped",
        "Perplexity is natively supported",
    ):
        assert forbidden.casefold() not in text.casefold()


def test_changed_markdown_relative_links_resolve_inside_repository():
    link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")

    for document in PUBLIC_DOCS:
        for raw_target in link_pattern.findall(_read(document)):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            relative = target.split("#", 1)[0]
            if not relative:
                continue
            resolved = (document.parent / relative).resolve()
            assert resolved.is_relative_to(REPO_ROOT.resolve()), (
                document,
                target,
            )
            assert resolved.exists(), (document, target)
