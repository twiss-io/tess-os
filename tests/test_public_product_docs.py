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
    REPO_ROOT / "docs" / "GITHUB_METADATA_RECOMMENDATION.md",
    REPO_ROOT / "adapters" / "CONFORMANCE.md",
    REPO_ROOT / "adapters" / "claude-code" / "README.md",
    REPO_ROOT / "adapters" / "codex" / "README.md",
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
        level_pattern = rf"\*\*{level}\b" if level != "C0" else rf"\({level}\)"
        assert re.search(
            rf"\| {re.escape(public_name)} \| [^\n]*{level_pattern}",
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
        "Unpublished documentation/metadata package for the Tess OS signed, "
        "fail-closed governance harness; runtime not included."
    )
    assert {"ai-governance", "review-gate", "claude-code", "codex"} <= set(
        root_package["keywords"]
    )

    assert wizard_package["version"] == "0.1.1"
    assert wizard_package["description"] == (
        "Guided local scaffolder for Tess OS; Claude Code is the default, with "
        "manual Codex and generic render-target opt-in."
    )
    assert {"ai-governance", "review-gate", "claude-code", "codex"} <= set(
        wizard_package["keywords"]
    )


def test_public_support_labels_use_the_verified_exact_vocabulary():
    exact_labels = (
        "C3 — Managed-adapter preview",
        "C2 — Manual-gated compatibility",
    )
    for relative in (
        "README.md",
        "docs/PLATFORM_SUPPORT.md",
        "docs/STATUS.md",
        "adapters/CONFORMANCE.md",
        "adapters/claude-code/README.md",
        "adapters/codex/README.md",
    ):
        document = _read(REPO_ROOT / relative)
        for label in exact_labels:
            if relative == "adapters/claude-code/README.md" and label.startswith("C2"):
                continue
            if relative == "adapters/codex/README.md" and label.startswith("C3"):
                continue
            assert label in document, (relative, label)


def test_codex_docs_distinguish_durable_surfaces_from_legacy_prompt_mirrors():
    codex = _read(REPO_ROOT / "adapters" / "codex" / "README.md")

    for claim in (
        "C2 — Manual-gated compatibility",
        "`AGENTS.md`",
        "`.codex/config.toml`",
        "`codex exec`",
        "does not discover this project's\n`.codex/prompts` directory",
        "loader is home-only",
        "top level of `$CODEX_HOME/prompts`",
        "https://learn.chatgpt.com/docs/custom-prompts",
        "./tessctl render --list-targets",
        "./tessctl render --target codex",
        '"enabled": ["claude-code", "codex"]',
    ):
        assert claim in codex

    assert "legacy/deprecated" in codex.casefold()

    for forbidden in (
        "ln -s",
        "~/.codex/prompts/tess-os",
        "use them as native",
        "native custom-prompt convention",
    ):
        assert forbidden not in codex


def test_npm_docs_disclose_live_and_unpublished_package_state():
    readme = _read(REPO_ROOT / "README.md")
    wizard_readme = _read(REPO_ROOT / "create-tess" / "README.md")
    root_package = _json(REPO_ROOT / "package.json")

    assert "https://www.npmjs.com/package/tess-os" not in readme
    assert "`tess-os` is **not published on npm**" in readme
    assert "registry's live `create-tess@0.1.0` is a legacy" in readme
    assert "registry's live `create-tess@0.1.0` is a legacy" in wizard_readme
    assert root_package["//"].startswith("UNPUBLISHED:")
    assert "runtime" in root_package["//"]
    assert "not available through an npm package" in root_package["//"]


def test_create_tess_documents_real_codex_opt_in_and_downstream_custody():
    wizard = _read(REPO_ROOT / "create-tess" / "README.md")

    for claim in (
        "There is no `create-tess` platform-selection flag or `tessctl enable-target`",
        "./tessctl render --list-targets",
        "./tessctl render --target codex",
        "./tessctl doctor",
        "./tessctl verify",
        '"enabled": ["claude-code", "codex"]',
        "./tessctl render --target generic",
        "that project's owner chooses\nand holds its external custody arrangement",
        "Xavier is the designated custodian only for the upstream\n`twiss-io/tess-os` repository",
    ):
        assert claim in wizard

    assert "Xavier for this repository" not in wizard


def test_github_metadata_change_is_exact_and_recommendation_only():
    recommendation = _read(
        REPO_ROOT / "docs" / "GITHUB_METADATA_RECOMMENDATION.md"
    )
    description = (
        "Signed, fail-closed review gate and model-neutral governance harness "
        "for coding-agent output."
    )
    topics = (
        "tess-os",
        "ai-governance",
        "coding-agents",
        "review-gate",
        "policy-as-code",
        "agent-orchestration",
        "claude-code",
        "openai-codex",
        "devsecops",
        "software-supply-chain",
    )

    assert "Recommendation only — not applied" in recommendation
    assert description in recommendation
    topic_block = recommendation.split("```text", 2)[2].split("```", 1)[0]
    assert tuple(line for line in topic_block.splitlines() if line) == topics
    assert "separate owner-authorized GitHub settings mutation" in recommendation


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
