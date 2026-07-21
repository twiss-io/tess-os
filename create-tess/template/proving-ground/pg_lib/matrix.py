"""The matrix: {weak, strong} model tiers x {bare, tess-os} scaffolds.

A `MatrixCell` is exactly what the mission brief specifies: "a cell = one
model x scaffold combo" — four cells total. Each cell is then run against
every selected task (and up to `--max-attempts` attempts per task); that
per-(cell, task, attempt) execution is a `Trial`, defined where it's
produced (`run.py`) rather than here, to keep this module to the small,
static piece: what the four cells ARE.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

MODEL_TIERS = ("weak", "strong")


@dataclass(frozen=True)
class MatrixCell:
    model_tier: str  # "weak" | "strong"
    model_id: str    # resolved --model value passed to `claude -p`
    scaffold: str    # "bare" | "tess-os"

    @property
    def cell_id(self) -> str:
        return f"{self.model_tier}-{self.scaffold}"


def build_matrix(model_tiers: List[str], scaffolds: List[str], model_ids: Dict[str, str]) -> List[MatrixCell]:
    """Build the requested subset of cells. `model_ids` maps tier -> the
    actual `--model` value (an alias like 'haiku'/'opus' or a full model
    name) — resolved once by the caller so this stays pure data assembly."""
    unknown_tiers = [t for t in model_tiers if t not in MODEL_TIERS]
    if unknown_tiers:
        raise ValueError(f"unknown model tier(s): {unknown_tiers}. Expected subset of {MODEL_TIERS}")
    missing_ids = [t for t in model_tiers if t not in model_ids]
    if missing_ids:
        raise ValueError(f"no model id configured for tier(s): {missing_ids}")

    return [
        MatrixCell(model_tier=tier, model_id=model_ids[tier], scaffold=scaffold)
        for tier in model_tiers
        for scaffold in scaffolds
    ]
