"""Tess OS second-brain onboarding (OOBE) package.

Stdlib only; runs on python3 >= 3.9 with no third-party modules, so
onboarding works even where tessctl's PyYAML preflight fails. Entry point:
scripts/brain/onboard.py. Contract: docs/brain/ONBOARDING.md.
"""

__all__ = ["state", "answers", "apply", "scaffold", "entities", "slug",
           "gitignore", "restore", "convert", "hook"]
