"""The anchor helpers exist once per trust root, by design: run-pinned.py
must not import tessctl, and the brain is a separate pinned closure. So the
copies must stay the same code. This compares their ASTs after removing
docstrings and annotations and mapping each copy's names onto run-pinned's,
the way tests/test_v1_lock_strict.py guards the strict lock reader."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUN_PINNED = REPO / ".claude" / "hooks" / "run-pinned.py"
TESSCTL = REPO / ".tess" / "bin" / "tessctl"
BRAIN_CONFIG = REPO / "scripts" / "brain" / "brainlib" / "config.py"

TESSCTL_NAMES = {
    "_os_user_home": "anchor_os_home",
    "_anchor_project_id": "anchor_project_id",
    "_anchor_git_common_dir": "anchor_git_common_dir",
    "_anchor_git_hooks_dir": "anchor_git_hooks_dir",
    "_anchor_file_path": "anchor_file_path",
}
BRAIN_NAMES = {"os_user_home": "anchor_os_home"}


class _Normalize(ast.NodeTransformer):
    def __init__(self, names):
        self.names = names

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.name = self.names.get(node.name, node.name)
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            node.body = body[1:]
        return node

    def visit_Name(self, node):
        node.id = self.names.get(node.id, node.id)
        return node


def _defs(path, names):
    out = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            key = names[node.name]
            out[key] = ast.dump(_Normalize(names).visit(node))
    return out


def test_tessctl_anchor_helpers_are_the_same_code_as_run_pinned():
    canonical = set(TESSCTL_NAMES.values())
    reference = _defs(RUN_PINNED, {n: n for n in canonical})
    copies = _defs(TESSCTL, TESSCTL_NAMES)
    assert set(reference) == canonical and set(copies) == canonical
    for name in sorted(canonical):
        assert copies[name] == reference[name], name


def test_brain_os_user_home_is_the_same_code_as_run_pinned():
    reference = _defs(RUN_PINNED, {"anchor_os_home": "anchor_os_home"})
    copy = _defs(BRAIN_CONFIG, BRAIN_NAMES)
    assert copy == reference and copy


def test_the_comparison_notices_a_drifted_copy(tmp_path):
    drifted = tmp_path / "tessctl"
    drifted.write_text(TESSCTL.read_text(encoding="utf-8").replace(
        'env["GIT_NO_REPLACE_OBJECTS"] = "1"\n    try:\n        r = subprocess.run(["git", "-C", str(root), "-c", "core.fsmonitor=false", "rev-list",',
        'try:\n        r = subprocess.run(["git", "-C", str(root), "-c", "core.fsmonitor=false", "rev-list",', 1),
        encoding="utf-8")
    reference = _defs(RUN_PINNED, {"anchor_project_id": "anchor_project_id"})
    assert _defs(drifted, TESSCTL_NAMES)["anchor_project_id"] != reference["anchor_project_id"]
