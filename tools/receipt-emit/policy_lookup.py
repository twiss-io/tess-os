# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""READ-ONLY lookup of a single fired policy rule from core/policy/policy.yaml
(or wherever `--policy` points), copied VERBATIM into the receipt's
`policy_decision` field (core/contracts/agent-receipt.schema.json's own
`PolicyDecision` shape). This module has NO write path to the policy file at
all — not "avoid writing" as a convention, but no code here ever opens the
file in a write mode — matching the task brief's "READ-ONLY — never modify
policy.yaml."

## Why this depends on PyYAML (and tools/receipt-verify does not)

`tools/receipt-verify/` is a THIRD-PARTY-AUDITOR-FACING tool — an outside
party is meant to run it with nothing but a receipt file and a public key,
so it is deliberately zero-third-party-dependency (stdlib + the system
`gpg` binary only; see that tool's own README "Why standalone").

`tools/receipt-emit/` is not that. It only makes sense to run FROM INSIDE a
Tess OS checkout — it reads THIS repository's own `core/policy/policy.yaml`,
a file with no meaning outside this project. `.tess/bin/tessctl` already
requires PyYAML to parse the exact same file (`requirements-dev.txt:
PyYAML>=6.0`, already installed in this repo's own CI and dev setup) — this
tool reuses that SAME already-required dependency rather than either (a)
hand-rolling a second, independent YAML parser whose whole job is to copy
policy prose VERBATIM (a parser that silently disagreed with tessctl's own
`_gate_load_policy` on any edge case — folded scalars, quoting, block
styles — would be a correctness/security regression on a rule-text field a
reader is meant to trust as authoritative, not an improvement), or
(b) inventing a policy-instance format of its own. Depending on an
already-shipped, already-tested repository dependency for a repository-
internal file is the safer engineering choice here, not a shortcut.
"""

from __future__ import annotations

from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover — exercised only in an environment
    # missing the SAME dependency .tess/bin/tessctl already requires.
    raise SystemExit(
        "tools/receipt-emit requires pyyaml (the same dependency "
        ".tess/bin/tessctl already requires — see requirements-dev.txt): "
        "pip install pyyaml"
    )

from errors import EmitRefused

PATH_RULE_REQUIRED = ("id", "description", "classification")
HARD_FLOOR_RULE_REQUIRED = ("id", "description", "category")


def _find_by_id(entries, rule_id: str):
    for entry in entries or []:
        if isinstance(entry, dict) and entry.get("id") == rule_id:
            return entry
    return None


def load_policy_rule(policy_path: str, rule_id: str) -> dict:
    """Returns a `PolicyDecision` dict — `source`/`rule_id`/`rule_kind`/
    (`classification` or `category`)/`description` — copied VERBATIM from
    whichever of `policy.rules[]` (path_rule) or `policy.hard_floor_rules[]`
    (hard_floor_rule) in `policy_path` contains an entry whose `id` equals
    `rule_id`.

    Fails closed (raises `EmitRefused`, never returns a partial/guessed
    result) if: the file cannot be read; it is not valid YAML; it has no
    top-level `policy` object; the rule id is not found in EITHER list; the
    rule id is found in BOTH lists (an authoring error in the policy file
    itself — never silently pick one); or the matched rule entry is missing
    a field this schema requires."""
    path = Path(policy_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise EmitRefused([f"could not read --policy file {policy_path!r}: {e}"])
    try:
        instance = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise EmitRefused([f"{policy_path!r} is not valid YAML: {e}"])

    policy = instance.get("policy") if isinstance(instance, dict) else None
    if not isinstance(policy, dict):
        raise EmitRefused([
            f"{policy_path!r} has no top-level 'policy' object — not a "
            f"valid policy.schema.json instance"
        ])

    path_rule = _find_by_id(policy.get("rules"), rule_id)
    hard_floor_rule = _find_by_id(policy.get("hard_floor_rules"), rule_id)

    if path_rule is not None and hard_floor_rule is not None:
        raise EmitRefused([
            f"rule id {rule_id!r} appears in BOTH policy.rules[] and "
            f"policy.hard_floor_rules[] in {policy_path!r} — ambiguous, "
            f"refusing rather than silently picking one"
        ])
    if path_rule is None and hard_floor_rule is None:
        raise EmitRefused([
            f"no rule with id {rule_id!r} found in policy.rules[] or "
            f"policy.hard_floor_rules[] of {policy_path!r}"
        ])

    if path_rule is not None:
        missing = [k for k in PATH_RULE_REQUIRED if k not in path_rule]
        if missing:
            raise EmitRefused([
                f"policy.rules[] entry {rule_id!r} in {policy_path!r} is "
                f"missing required field(s) {missing}"
            ])
        return {
            "source": policy_path,
            "rule_id": path_rule["id"],
            "rule_kind": "path_rule",
            "classification": path_rule["classification"],
            "description": path_rule["description"],
        }

    missing = [k for k in HARD_FLOOR_RULE_REQUIRED if k not in hard_floor_rule]
    if missing:
        raise EmitRefused([
            f"policy.hard_floor_rules[] entry {rule_id!r} in {policy_path!r} "
            f"is missing required field(s) {missing}"
        ])
    return {
        "source": policy_path,
        "rule_id": hard_floor_rule["id"],
        "rule_kind": "hard_floor_rule",
        "category": hard_floor_rule["category"],
        "description": hard_floor_rule["description"],
    }
