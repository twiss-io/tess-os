"""Entities and cards: create-only, index line first (spec sections 6.4, 8).

An entity is a folder with an `AGENTS.md` that starts `# START HERE: <name>`
plus the `CLAUDE.md` / `GEMINI.md` import shims. A card is a single file
(person, seat). Every new entity gets one row in brain/START-HERE.md's
`## Entities` table; every new card gets one row in its parent AGENTS.md
`## Where things are` table. The index row is written BEFORE the files, so
a half-finished add is still reachable from the map.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import scaffold, state
from .slug import cell, name_key, one_line, slugify

START_HERE = "brain/START-HERE.md"


def kind_spec(brain: Dict[str, Any], kind: str, mode: Optional[str] = None) -> Dict[str, Any]:
    """The first active mode (or --mode) whose manifest defines this kind."""
    modes = [mode] if mode else list(brain.get("modes") or [])
    known: List[str] = []
    for name in modes:
        kinds = scaffold.load_manifest("modes", name).get("kinds", {})
        known.extend(k for k in kinds if k not in known)
        if kind in kinds:
            spec = dict(kinds[kind])
            spec["mode"] = name
            return spec
    raise state.BrainError("no mode in %s defines %r; kinds here: %s"
                           % (modes, kind, ", ".join(known) or "none"), 2)


def entity_ctx(base: Dict[str, Any], kind: str, name: str, slug: str, rel_dir: str,
               extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ctx = dict(base)
    ctx.update({"name": one_line(name, 80), "slug": slug, "kind": kind,
                "id": rel_dir[len("brain/"):] if rel_dir.startswith("brain/") else rel_dir})
    ctx.update(extra or {})
    return ctx


def insert_row(plan: scaffold.Plan, index_rel: str, heading: str, row: str, key: str) -> str:
    """Append a Markdown table row under `heading` unless `key` is already there."""
    path = plan.root / index_rel
    if not path.exists():
        return "missing index %s" % index_rel
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == heading)
    except StopIteration:
        return "no %r section in %s" % (heading, index_rel)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("#") or lines[i].startswith("<!-- tess:gen:"):
            end = i
            break
    block = lines[start + 1:end]
    if any(key in ln for ln in block):
        return "indexed"
    last = max((i for i in range(start + 1, end) if lines[i].strip()), default=start)
    lines.insert(last + 1, row)
    if not plan.dry:
        state.atomic_write(path, "\n".join(lines))
    plan.actions.append(("indexed", index_rel))
    return "indexed"


def link(from_file: str, target: str) -> str:
    return os.path.relpath(target, os.path.dirname(from_file)).replace(os.sep, "/")


def create_entity(plan: scaffold.Plan, template: str, rel_dir: str, ctx: Dict[str, Any]) -> None:
    """Index row first, then files (create-only), then the import shims."""
    agents = "%s/AGENTS.md" % rel_dir
    row = "| %s | %s | [%s](%s) |" % (cell(ctx["name"]), ctx["kind"], agents, link(START_HERE, agents))
    insert_row(plan, START_HERE, "## Entities", row, "](%s)" % link(START_HERE, agents))
    scaffold.materialize(plan, template, rel_dir, ctx)
    scaffold.add_shims(plan, rel_dir)


def create_card(plan: scaffold.Plan, template: str, rel_file: str, index_rel: str,
                ctx: Dict[str, Any]) -> None:
    target = link(index_rel, rel_file)
    row = "| %s (%s) | [%s](%s) |" % (cell(ctx["name"]), ctx["kind"], target, target)
    insert_row(plan, index_rel, "## Where things are", row, "](%s)" % target)
    scaffold.materialize(plan, template, rel_file, ctx)


def existing_name(path) -> Optional[str]:
    """The `name:` front-matter value of an existing entity/card file, if any."""
    try:
        head = path.read_text(encoding="utf-8").split("\n", 40)[:40]
    except (OSError, UnicodeDecodeError):
        return None
    for line in head:
        if line.startswith("name: "):
            raw = line[len("name: "):].strip()
            try:
                return str(json.loads(raw))
            except ValueError:
                return raw
    return None


def claim_slug(plan: scaffold.Plan, spec: Dict[str, Any], name: str, parent: str) -> str:
    """The slug for `name`: the base slug unless a DIFFERENT entity already holds it.

    Same entity (same name_key, or a hand-made file with no `name:`) keeps the
    base slug, so the caller reports 'skipped (exists)' and changes nothing.
    A different display name gets -2, -3, ...: never 'skipped' for another entity.
    """
    base = slugify(name)
    claimed = plan.__dict__.setdefault("claimed", {})
    for n in range(1, 100):
        slug = base if n == 1 else "%s-%d" % (base, n)
        dest = spec["dest"].format(slug=slug, parent=parent)
        target = dest + "/AGENTS.md" if spec.get("entity") else dest
        other = claimed.get(target)
        if other is None and (plan.root / target).exists():
            other = existing_name(plan.root / target) or name
        if other is None or name_key(other) == name_key(name):
            claimed[target] = name
            return slug
    raise state.BrainError("too many entities share the slug %r" % base, 3)


def add(plan: scaffold.Plan, brain: Dict[str, Any], base_ctx: Dict[str, Any], kind: str,
        name: str, parent: Optional[str] = None, mode: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None) -> str:
    """Create one entity or card of `kind`. Returns its repo-relative path."""
    name = " ".join(str(name).split())
    if not name_key(name):
        raise state.BrainError("add %s: the name %r has no letters or digits" % (kind, name), 2)
    spec = kind_spec(brain, kind, mode)
    if spec.get("needs_parent") and not parent:
        raise state.BrainError("add %s needs --in <%s-slug>" % (kind, spec["needs_parent"]), 2)
    base = slugify(name)
    fields = {"parent": slugify(parent) if parent else ""}
    fields["slug"] = slug = claim_slug(plan, spec, name, fields["parent"])
    template = spec["template"]
    if base in spec.get("private_slugs", []):
        template = spec.get("private_template", template)
    dest = spec["dest"].format(**fields)
    ctx = entity_ctx(base_ctx, kind, name, slug, dest, extra)
    ctx["privacy"] = spec.get("privacy", "internal")
    if spec.get("entity"):
        create_entity(plan, template, dest, ctx)
    else:
        create_card(plan, template, dest, spec["index"].format(**fields), ctx)
    if base in spec.get("private_slugs", []) and not plan.dry:
        state.ensure_local_dir(plan.root / "brain" / ".private")
        (plan.root / "brain" / ".private" / "areas" / slug).mkdir(parents=True, exist_ok=True)
    return dest


def add_base(plan: scaffold.Plan, manifest: Dict[str, Any], base_ctx: Dict[str, Any]) -> None:
    """A mode's fixed entities (brain/agency, brain/org, brain/life)."""
    for item in manifest.get("base", []):
        ent = item["entity"]
        name = scaffold.render(ent["name"], base_ctx)
        ctx = entity_ctx(base_ctx, ent["kind"], name, ent["id"], item["dest"])
        ctx["privacy"] = ent.get("privacy", "internal")
        create_entity(plan, item["template"], item["dest"], ctx)


def update_mode_line(plan: scaffold.Plan, modes_line: str) -> None:
    """Keep START-HERE's one `- Mode:` line in step with brain.json (add-mode)."""
    path = plan.root / START_HERE
    if plan.dry or not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    new = re.sub(r"(?m)^- Mode: .*?(?=\. Preset: |$)", lambda m: "- Mode: %s" % modes_line, text, count=1)
    if new != text:
        state.atomic_write(path, new)
        plan.actions.append(("updated", START_HERE))


def start_here_budget_warning(root: Path, brain: Dict[str, Any]) -> str:
    """One warning line when brain/START-HERE.md is over its budget, else ''.

    `add` only warns; `tessbrain.py lint` (when installed) is the enforcement point."""
    path = root / START_HERE
    if not path.is_file():
        return ""
    budgets = dict(state.BUDGETS)
    budgets.update(brain.get("budgets") or {})
    data = path.read_bytes()
    lines, size = data.count(b"\n"), len(data)
    max_lines, max_bytes = int(budgets["start_here_lines"]), int(budgets["start_here_kib"]) * 1024
    if lines <= max_lines and size <= max_bytes:
        return ""
    return ("warning: %s is %d lines / %d B, over its budget (%d lines / %d B); move rows into "
            "brain/index/ or consolidate (`python3 scripts/brain/tessbrain.py lint` enforces this)"
            % (START_HERE, lines, size, max_lines, max_bytes))
