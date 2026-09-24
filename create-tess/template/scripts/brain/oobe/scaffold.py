"""Create-only template materialisation (spec section 8).

Templates live in scripts/brain/templates/. A template file's path and body
may use {{key}} (raw) and {{key_q}} (JSON/YAML-quoted) placeholders; a
trailing `.tpl` is stripped from file names. Nothing here ever overwrites,
moves or renames an existing path: an existing file is reported as
`skipped (exists)` and its bytes are left untouched.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import state

BRAIN_TOOLS = Path(__file__).resolve().parents[1]  # scripts/brain
TEMPLATES = BRAIN_TOOLS / "templates"
_TOKEN = re.compile(r"\{\{([a-z0-9_]+)\}\}")

Action = Tuple[str, str]  # (action, repo-relative path)


class Plan:
    """Collects actions; writes files unless dry-run."""

    def __init__(self, root: Path, dry: bool = False):
        self.root = root
        self.dry = dry
        self.actions: List[Action] = []

    def create(self, rel: str, text: str) -> bool:
        path = self.root / rel
        if path.exists() or any(a == "created" and p == rel for a, p in self.actions):
            self.actions.append(("skipped (exists)", rel))
            return False
        if not self.dry:
            state.atomic_write(path, text)
        self.actions.append(("created", rel))
        return True

    def created(self) -> List[str]:
        return [p for a, p in self.actions if a == "created"]


def render(text: str, ctx: Dict[str, Any]) -> str:
    """Substitute {{key}} / {{key_q}}. Unknown keys are an error (no silent gaps)."""

    def sub(match):
        key = match.group(1)
        if key.endswith("_q") and key[:-2] in ctx:
            return json.dumps(ctx[key[:-2]], ensure_ascii=False)
        if key in ctx:
            value = ctx[key]
            return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        raise state.BrainError("template placeholder {{%s}} has no value" % key, 5)

    return _TOKEN.sub(sub, text)


def template_files(rel: str) -> List[Tuple[Path, str]]:
    """(source, relative-output-path) for a template file or directory."""
    src = TEMPLATES / rel
    if src.is_file():
        return [(src, "")]
    if not src.is_dir():
        raise state.BrainError("missing template %s" % rel, 5)
    out = []
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        out.append((path, path.relative_to(src).as_posix()))
    return out


def _out_name(rel: str) -> str:
    return rel[:-4] if rel.endswith(".tpl") else rel


def materialize(plan: Plan, template: str, dest: str, ctx: Dict[str, Any]) -> List[str]:
    """Copy one template file/dir to dest (create-only). Returns created paths."""
    made = []
    for src, rel in template_files(template):
        target = dest if not rel else "%s/%s" % (dest, _out_name(rel))
        target = render(target, ctx)
        if plan.create(target, render(src.read_text(encoding="utf-8"), ctx)):
            made.append(target)
    return made


def add_shims(plan: Plan, entity_dir: str) -> None:
    """CLAUDE.md = '@AGENTS.md' and GEMINI.md = '@./AGENTS.md' beside AGENTS.md."""
    for name in ("CLAUDE.md", "GEMINI.md"):
        text = (TEMPLATES / "shims" / name).read_text(encoding="utf-8")
        plan.create("%s/%s" % (entity_dir, name), text)


def load_manifest(kind: str, name: str) -> Dict[str, Any]:
    """modes/<name>.json or presets/<name>.json."""
    path = BRAIN_TOOLS / kind / ("%s.json" % name)
    if not path.exists():
        raise state.BrainError("unknown %s %r" % (kind[:-1], name), 2)
    return json.loads(path.read_text(encoding="utf-8"))


def core_seeds(plan: Plan, ctx: Dict[str, Any]) -> None:
    """brain core seeds (START-HERE, generated stubs, folders) + local dirs."""
    for src, rel in template_files("core"):
        target = render(_out_name(rel), ctx)
        body = src.read_text(encoding="utf-8")
        # brain/README.md belongs to the learning workstream: copied verbatim.
        plan.create(target, body if rel == "brain/README.md" else render(body, ctx))
    if not plan.dry:
        state.ensure_local_dir(plan.root / "brain" / ".private")


def entity_roots(modes: List[str]) -> List[str]:
    roots: List[str] = []
    for mode in modes:
        for item in load_manifest("modes", mode).get("entity_roots", []):
            if item not in roots:
                roots.append(item)
    return roots
