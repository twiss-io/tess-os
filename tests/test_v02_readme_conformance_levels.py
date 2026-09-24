"""
v0.2.0 (ws-hyg): the enforcement levels that README.md and docs/STATUS.md
claim for each coding-agent runtime must equal the levels in
adapters/CONFORMANCE.md, which holds the evidence and documentation links.

Without this test the three pages can disagree silently: a reviewer found
README and STATUS saying Gemini CLI was Partial while the shipped conformance
row, the Gemini adapter README and the Gemini adapter manifest all said
Advisory. No check failed.

What is pinned:
  * README "Runtimes and enforcement" table and the STATUS "Runtime
    enforcement levels" table: every runtime a row names has a
    CONFORMANCE row, and the levels are equal.
  * Every runtime CONFORMANCE lists is named in each of those tables
    (a runtime cannot fall into the "any runtime not listed here" row by
    omission). Only the two catch-all CONFORMANCE rows are exempt, and
    each is compared with its README/STATUS catch-all row instead.
  * A table row that says "`<key>` target" names a key registered in the
    engine's RENDER_TARGETS, and CONFORMANCE gives the same runtime that
    same Tess target. If a render target is dropped from a release, the
    README cannot keep describing it.
  * The STATUS matrix "Enforcement level **X**" cells for each render
    target, and the STATUS fact "Gemini CLI is X", agree with CONFORMANCE.

The per-runtime CONFORMANCE table ships with the v0.2.0 runtime work
(v0.2/rt). On a tree without it, the module skips. Once that table exists,
tests/test_v02_conformance_doc.py fails if it is removed, so this skip
cannot hide a missing table.
"""

from __future__ import annotations

import re

import pytest

from conftest import REPO_ROOT

CONFORMANCE = REPO_ROOT / "adapters" / "CONFORMANCE.md"
README = REPO_ROOT / "README.md"
STATUS = REPO_ROOT / "docs" / "STATUS.md"

_CONF_HEADER = ["Runtime", "Tess target", "Level", "How it reads Tess", "Why this level (limits)", "Docs"]
_README_HEADER = ["Runtime", "Enforcement", "How Tess OS reaches it", "Main limits"]
_STATUS_HEADER = ["Runtime", "Enforcement", "Basis and limits"]

# CONFORMANCE rows that are catch-alls, not a named runtime.
_CONF_GENERIC = "any agents.md reader"
_CONF_OTHER = "any other runtime"


def _split_row(line: str) -> list:
    # Split on pipes that are not escaped (`\|` inside a code span).
    cells = re.split(r"(?<!\\)\|", line.strip())
    return [c.strip() for c in cells[1:-1]]


def _table(path, header) -> list:
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("|") and _split_row(line) == header:
            rows = []
            for row_line in lines[i + 2:]:
                if not row_line.startswith("|"):
                    break
                cells = _split_row(row_line)
                assert len(cells) == len(header), f"{path.name}: {row_line}"
                rows.append(dict(zip(header, cells)))
            return rows
    return []


def _norm(name: str) -> str:
    name = name.replace("`", "")
    name = re.sub(r"\([^)]*\)", "", name)
    name = re.sub(r"^(OpenAI|Google)\s+", "", name.strip())
    return re.sub(r"\s+", " ", name).strip().lower()


def _level(cell: str) -> str:
    m = re.search(r"\*\*([^*]+)\*\*", cell)
    assert m, f"no bold level in cell: {cell!r}"
    return m.group(1).strip()


def _target_key(cell: str):
    m = re.fullmatch(r"`([a-z0-9-]+)`", cell.strip())
    return m.group(1) if m else None


def _conformance() -> dict:
    """normalised runtime name -> {"level": ..., "target": key or None}."""
    out = {}
    for row in _table(CONFORMANCE, _CONF_HEADER):
        out[_norm(row["Runtime"])] = {
            "level": row["Level"],
            "target": _target_key(row["Tess target"]),
            "raw": row["Runtime"],
        }
    return out


if not _table(CONFORMANCE, _CONF_HEADER):
    pytest.skip(
        "adapters/CONFORMANCE.md has no per-runtime table on this tree; it "
        "lands with the v0.2.0 runtime work (v0.2/rt)",
        allow_module_level=True,
    )


def _parse_claim_rows(path, header, how_col):
    """Return (named, catch_all_other, catch_all_agents_md, target_claims).

    named: {normalised runtime: (level, row text)}
    catch_all_other: level of the "any runtime not listed here" row
    catch_all_agents_md: level of the "Other AGENTS.md tools" row
    target_claims: [(runtime names, target key)] for "`key` target" cells
    """
    rows = _table(path, header)
    assert rows, f"{path.name} has no runtime enforcement table with header {header}"
    named, other, agents_md, targets = {}, None, None, []
    for row in rows:
        cell = row["Runtime"]
        level = _level(row["Enforcement"])
        m = re.search(r"\(for example ([^)]*)\)", cell)
        if cell.replace("`", "").lower().startswith("other agents.md tools"):
            assert agents_md is None, f"{path.name}: two 'Other AGENTS.md tools' rows"
            agents_md = level
            assert m, f"{path.name}: the AGENTS.md row names no examples: {cell!r}"
            names = [n for n in re.split(r",\s*", m.group(1)) if n.strip()]
        else:
            if "not listed" in cell:
                assert other is None, f"{path.name}: two catch-all rows"
                other = level
                cell = re.sub(r",?\s*(and\s+)?any runtime not listed here", "", cell)
            names = [n for n in re.split(r",\s*(?:and\s+)?|\s+and\s+", cell) if n.strip()]
        row_names = []
        for n in names:
            key = _norm(n)
            assert key not in named, f"{path.name} names {n!r} twice"
            named[key] = (level, row["Runtime"])
            row_names.append(key)
        t = re.search(r"`([a-z0-9-]+)` target", row[how_col])
        if t:
            targets.append((row_names, t.group(1)))
    return named, other, agents_md, targets


_CLAIM_PAGES = [
    pytest.param(README, _README_HEADER, "How Tess OS reaches it", id="README"),
    pytest.param(STATUS, _STATUS_HEADER, "Basis and limits", id="STATUS"),
]


@pytest.mark.parametrize("path,header,how_col", _CLAIM_PAGES)
def test_every_named_runtime_level_matches_conformance(path, header, how_col):
    conf = _conformance()
    named, _, _, _ = _parse_claim_rows(path, header, how_col)
    mismatches = []
    for name, (level, row) in named.items():
        assert name in conf, (
            f"{path.name} row {row!r} names {name!r}, which adapters/CONFORMANCE.md "
            f"does not list (known: {sorted(conf)})"
        )
        if conf[name]["level"] != level:
            mismatches.append(f"{name}: {path.name} says {level}, CONFORMANCE says {conf[name]['level']}")
    assert not mismatches, "; ".join(mismatches)


@pytest.mark.parametrize("path,header,how_col", _CLAIM_PAGES)
def test_every_conformance_runtime_is_named(path, header, how_col):
    conf = _conformance()
    named, _, _, _ = _parse_claim_rows(path, header, how_col)
    missing = [
        conf[k]["raw"] for k in conf
        if k not in (_CONF_GENERIC, _CONF_OTHER) and k not in named
    ]
    assert not missing, (
        f"{path.name}'s runtime table omits {missing}; they would fall under "
        f"'any runtime not listed here' although CONFORMANCE gives them a level"
    )


@pytest.mark.parametrize("path,header,how_col", _CLAIM_PAGES)
def test_catch_all_rows_match_conformance(path, header, how_col):
    conf = _conformance()
    _, other, agents_md, _ = _parse_claim_rows(path, header, how_col)
    assert _CONF_OTHER in conf and _CONF_GENERIC in conf, sorted(conf)
    assert other == conf[_CONF_OTHER]["level"], (path.name, other, conf[_CONF_OTHER])
    assert agents_md == conf[_CONF_GENERIC]["level"], (path.name, agents_md, conf[_CONF_GENERIC])


@pytest.mark.parametrize("path,header,how_col", _CLAIM_PAGES)
def test_named_render_targets_are_registered_and_agree(engine, path, header, how_col):
    conf = _conformance()
    _, _, _, targets = _parse_claim_rows(path, header, how_col)
    registered = set(engine.RENDER_TARGETS)
    assert targets, f"{path.name}: no row names a `<key>` target"
    for names, key in targets:
        assert key in registered, (
            f"{path.name} describes the `{key}` target, which is not in "
            f"RENDER_TARGETS {sorted(registered)}"
        )
        for name in names:
            assert conf[name]["target"] == key, (
                f"{path.name} says {name!r} uses the `{key}` target; "
                f"CONFORMANCE says {conf[name]['target']!r}"
            )


# STATUS "Current matrix": the render-target rows carry "Enforcement level **X**".
_MATRIX_TARGETS = {
    "Claude Code target and driver": "claude-code",
    "Codex target and driver": "codex",
    "Gemini CLI target": "gemini",
    "Generic `AGENTS.md` target": "generic",
}


def test_status_matrix_target_levels_match_conformance(engine):
    conf = _conformance()
    by_target = {v["target"]: v["level"] for v in conf.values() if v["target"]}
    text = STATUS.read_text(encoding="utf-8")
    checked = 0
    for label, key in _MATRIX_TARGETS.items():
        m = re.search(r"^\| " + re.escape(label) + r" \|[^\n]*?[Ee]nforcement level \*\*([^*]+)\*\*", text, re.M)
        if key not in engine.RENDER_TARGETS:
            assert m is None, f"STATUS matrix describes {label!r} but `{key}` is not registered"
            continue
        assert m, f"STATUS matrix has no 'Enforcement level' for {label!r}"
        assert m.group(1) == by_target[key], (label, m.group(1), by_target[key])
        checked += 1
    assert checked >= 3


def test_status_gemini_fact_matches_conformance():
    conf = _conformance()
    m = re.search(r"\*\*Gemini CLI is (\w+)", STATUS.read_text(encoding="utf-8"))
    if "gemini cli" not in conf or conf["gemini cli"]["target"] != "gemini":
        assert m is None, "STATUS states a Gemini CLI level but no `gemini` target is conformance-listed"
        return
    assert m, "STATUS has no 'Gemini CLI is <level>' fact"
    assert m.group(1) == conf["gemini cli"]["level"], (m.group(1), conf["gemini cli"])
