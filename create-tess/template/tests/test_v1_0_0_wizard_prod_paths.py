"""The wizard's production paths and the first-push check agree exactly.

create-tess (src/prod-paths.js) replaces the shipped policy's placeholder
glob `__REPLACE_ME__/prod/**` with the adopter's folders. The first push of a
fresh install is accepted without a verdict only when Tess's files are the
signed release with the wizard's changes, so tessctl must accept exactly the
lines the wizard writes (`_policy_with_prod_paths_ok`) and nothing more. The
end-to-end first push is in test_v1_first_push_release_proof.py."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
JS = REPO / "create-tess" / "src" / "prod-paths.js"
PLACEHOLDER = '        - "__REPLACE_ME__/prod/**"\n'


@pytest.fixture(scope="module")
def wizard_text(engine):
    return engine._policy_reset_registries_text((REPO / "core/policy/policy.yaml").read_text(encoding="utf-8"))


def _with(text, *lines):
    return text.replace(PLACEHOLDER, "".join(lines), 1)


def test_the_release_policy_has_the_placeholder_exactly_once(wizard_text):
    assert wizard_text.count(PLACEHOLDER) == 1


@pytest.mark.parametrize("globs", [["src/**"], ["src/**", "api/**"], ["infra/prod/*.tf"],
                                   [f"d{i}/**" for i in range(20)], ["apps/web-1/**", ".config/x"]])
def test_the_wizard_edit_is_accepted(engine, wizard_text, globs):
    mine = _with(wizard_text, *[f'        - "{g}"\n' for g in globs])
    assert engine._policy_with_prod_paths_ok(wizard_text, mine) is True


BAD = {
    "unchanged (that is the plain reset, not this edit)": lambda t: t,
    "no glob lines": lambda t: _with(t, ""),
    "21 globs": lambda t: _with(t, *[f'        - "d{i}/**"\n' for i in range(21)]),
    "duplicate glob": lambda t: _with(t, '        - "src/**"\n', '        - "src/**"\n'),
    "absolute": lambda t: _with(t, '        - "/etc/**"\n'),
    "dot-dot": lambda t: _with(t, '        - "a/../b/**"\n'),
    "match everything": lambda t: _with(t, '        - "**"\n'),
    "placeholder kept": lambda t: _with(t, PLACEHOLDER, '        - "src/**"\n'),
    "space in glob": lambda t: _with(t, '        - "my app/**"\n'),
    "quote injection": lambda t: _with(t, '        - "src/**"\n      require_verdict: false\n'),
    "colon": lambda t: _with(t, '        - "a: b"\n'),
    "wrong indent": lambda t: _with(t, '      - "src/**"\n'),
    "unquoted": lambda t: _with(t, "        - src/**\n"),
    "trailing text": lambda t: _with(t, '        - "src/**" # x\n'),
    "no final newline": lambda t: _with(t, '        - "src/**"'),
    "CRLF": lambda t: _with(t, '        - "src/**"\r\n'),
    "another byte changed": lambda t: _with(t, '        - "src/**"\n').replace(
        "require_verdict: true", "require_verdict: false", 1),
    "allowed_verifiers widened": lambda t: _with(t, '        - "src/**"\n').replace(
        "allowed_verifiers: [Reid, Quinn]", "allowed_verifiers: [Reid, Quinn, Mallory]", 1),
    "verifier key added": lambda t: _with(t, '        - "src/**"\n').replace(
        "verifier_keys: {}", 'verifier_keys:\n    M:\n      fingerprint: "' + "A" * 40 + '"', 1),
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_anything_else_is_refused(engine, wizard_text, name):
    assert engine._policy_with_prod_paths_ok(wizard_text, BAD[name](wizard_text)) is False


def test_a_template_without_the_placeholder_accepts_nothing(engine, wizard_text):
    edited = _with(wizard_text, '        - "src/**"\n')
    assert engine._policy_with_prod_paths_ok(edited, _with(edited, '        - "api/**"\n')) is False


def test_python_accepts_exactly_what_the_wizard_writes(engine, wizard_text, tmp_path):
    if not (shutil.which("node") and JS.is_file()):
        pytest.skip("Tess OS source repo with node only")
    inputs = ["src", "src, api/**", "./apps/web/, infra/prod/*.tf", ",".join(f"d{i}" for i in range(20)),
              "../x", "/abs", "**", "a b", 'a"b', ",".join(f"d{i}" for i in range(21)), ""]
    (tmp_path / "in.json").write_text(json.dumps({"text": wizard_text, "inputs": inputs}))
    script = (f"import {{ parseProdPaths, applyProdPaths }} from {json.dumps(JS.as_uri())};"
              "import { readFileSync } from 'node:fs';"
              f"const d = JSON.parse(readFileSync({json.dumps(str(tmp_path / 'in.json'))}, 'utf8'));"
              "process.stdout.write(JSON.stringify(d.inputs.map((raw) => {"
              "  const r = parseProdPaths(raw);"
              "  return r.ok ? applyProdPaths(d.text, r.value) : null; })));")
    out = json.loads(subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True,
                                    text=True, check=True, cwd=str(tmp_path)).stdout)
    for raw, res in zip(inputs, out):
        if res is None:
            assert raw in ("../x", "/abs", "**", "a b", 'a"b') or raw.count(",") == 20, raw
        elif res["changed"]:
            assert engine._policy_with_prod_paths_ok(wizard_text, res["text"]) is True, raw
        else:
            assert raw == "" and res["text"] == wizard_text
