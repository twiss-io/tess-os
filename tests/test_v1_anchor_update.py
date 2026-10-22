"""v1.0.0: `tessctl update` / `self-update` write the enforcement anchor after a
verified signed release is applied, and refuse to run (so never re-bless)
while Tess's safety files differ from the anchor. The anchor goes to the fake
OS-record home (fixtures.os_home), never the real ~/.config.
"""
from __future__ import annotations

import json

import pytest

from conftest import ENGINE_SRC, make_upstream, ns
from fixtures.os_home import operator_home  # noqa: F401 — autouse: fake OS-record home
from test_v1_integration import GUARD_KEY, NEW, _installed_instance, _update, needs_gpg


@needs_gpg
def test_update_records_the_anchor_after_a_verified_release(project, gpg_key, tmp_path, run_cli,
                                                           operator_home):  # noqa: F811
    _installed_instance(project, gpg_key, tmp_path, run_cli)
    assert project.mod._anchor_state(project.root).state == "none"
    _update(project, run_cli)
    st = project.mod._anchor_state(project.root)
    assert st.state == "ok", st.problems
    assert st.doc["source"] == "update" and st.doc["release"] == "2.1.0"
    assert st.where.startswith(str(operator_home / "tess" / "projects"))
    assert ".tess/tess.lock" in st.doc["files"] and ".claude/settings.json" in st.doc["files"]


@needs_gpg
def test_update_refuses_while_safety_files_differ_from_the_anchor(project, gpg_key, tmp_path,
                                                                 run_cli):
    _installed_instance(project, gpg_key, tmp_path, run_cli)
    project.mod._anchor_write(project.root, "test")
    settings = project.root / ".claude" / "settings.json"
    settings.write_text(json.dumps({"hooks": {}, "disableAllHooks": True}) + "\n")
    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    assert r.returncode != 0
    assert "Tess's safety files have changed" in r.stdout + r.stderr
    assert project.core(GUARD_KEY).read_text(encoding="utf-8") != NEW, "nothing was updated"
    assert project.mod._anchor_state(project.root).state == "mismatch", "and nothing re-blessed"


@pytest.mark.skipif(not ENGINE_SRC.is_file(), reason="engine missing")
def test_self_update_records_the_anchor(project, gpg_key, tmp_path):
    up = make_upstream(tmp_path / "up_anchor", gpg_key, "v2.0.1", sign="signed",
                       core_files={".tess/core/conductor/guardrails.md": "g\n"},
                       engine_bytes=ENGINE_SRC.read_bytes() + b"\n# anchor test\n")
    project.add("conductor/a.md", "alpha\n")
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.write()
    project.mod.cmd_self_update(ns(ref="v2.0.1", to=None, trust_on_first_use=True), project.root)
    st = project.mod._anchor_state(project.root)
    assert st.state == "ok" and st.doc["source"] == "self-update", (st.state, st.problems)
    assert ".tess/bin/tessctl" in st.doc["files"]
