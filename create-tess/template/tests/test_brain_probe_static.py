"""scripts/brain/probe.py --static: the zero-context fresh-clone probe (O13, spec 15.5).

The probe must answer from a CLONE (so only committed files count), must
route through START-HERE -> entity AGENTS.md -> decisions rather than read
probe.json's expectations back, must fail on an un-onboarded clone, and must
fail its negative control when the brain holds what it never should.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import _brain_oobe_helpers as h


def probe(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(root / "scripts" / "brain" / "probe.py"), "--static"]
                          + list(extra), cwd=str(root), capture_output=True, text=True, timeout=60)


def clone(src: Path, dest: Path) -> Path:
    done = subprocess.run(["git", "clone", "-q", str(src), str(dest)], capture_output=True, text=True,
                          env=h.env())
    assert done.returncode == 0, done.stderr
    return dest


@pytest.fixture(scope="module")
def onboarded_clone(tmp_path_factory):
    base = tmp_path_factory.mktemp("probe")
    root = h.mini_instance(base)
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    return clone(root, base / "clone")


def test_clone_passes_with_every_answer_from_files(onboarded_clone):
    done = probe(onboarded_clone, "--json")
    assert done.returncode == 0, done.stdout + done.stderr
    out = json.loads(done.stdout)
    assert out["result"] == "pass" and out["score"] == out["total"] == 5
    got = {a["id"]: a["answer"] for a in out["answers"]}
    assert got["mode"] == ["agency"]
    assert got["operator"] == "Mira Okafor"
    assert got["entities"] == ["agency", "clients/bluefin-labs", "clients/northwind-studio"]
    assert got["first-decision"] == {"id": "D-20260924-1015-brain-mode",
                                     "quote": "An agency: I run a small consultancy serving outside clients."}
    assert got["research"] == "brain/kb/research/"
    assert out["negative_control"]["answer"] == "unknown" and out["negative_control"]["ok"]


def test_unonboarded_clone_fails(tmp_path):
    root = h.mini_instance(tmp_path)
    (root / "README.md").write_text("instance\n")
    h.git(root, "add", "-A")
    h.git(root, "commit", "-qm", "seed")
    done = probe(clone(root, tmp_path / "clone"), "--json")
    assert done.returncode == 1
    assert "not an onboarded brain" in json.loads(done.stdout)["reason"]


def test_answers_come_from_routing_not_from_probe_json(tmp_path):
    """Breaking the map (START-HERE) breaks the answers even though probe.json is intact."""
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    start = root / "brain" / "START-HERE.md"
    text = start.read_text()
    text = text.replace("- Operator: Mira Okafor", "- Operator: someone")
    text = text.replace("| Research |", "| Findings |")
    start.write_text(text)
    done = probe(root, "--json")
    out = json.loads(done.stdout)
    assert done.returncode == 1 and out["score"] == 3
    assert {a["id"] for a in out["answers"] if not a["ok"]} == {"operator", "research"}


def test_entity_without_start_here_is_not_counted(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "agency-solo").returncode == 0
    agents = root / "brain" / "clients" / "bluefin-labs" / "AGENTS.md"
    agents.write_text(agents.read_text().replace("# START HERE:", "# Notes:"))
    out = json.loads(probe(root, "--json").stdout)
    ent = next(a for a in out["answers"] if a["id"] == "entities")
    assert ent["ok"] is False and "clients/bluefin-labs" not in ent["answer"]


def test_negative_control_fails_when_the_brain_holds_a_bank_account(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "personal").returncode == 0
    (root / "brain" / "facts" / "F-x.md").write_text("Bank account: 012-345678-9\n")
    done = probe(root, "--json")
    out = json.loads(done.stdout)
    assert done.returncode == 1 and out["score"] == 5
    assert out["negative_control"]["answer"] == "found"


def test_private_dir_is_not_scanned(tmp_path):
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "personal").returncode == 0
    (root / "brain" / ".private" / "money.md").write_text("Bank account: 012-345678-9\n")
    assert probe(root).returncode == 0


def test_static_flag_is_required(tmp_path):
    done = subprocess.run([sys.executable, str(h.BRAIN_TOOLS / "probe.py")], capture_output=True, text=True)
    assert done.returncode == 2 and "--static" in done.stderr


def test_probe_stays_green_as_the_brain_grows(tmp_path):
    """add / add-mode keep probe.json's expectations in step: no false red after normal use."""
    root = h.mini_instance(tmp_path)
    assert h.onboard_fixture(root, "personal").returncode == 0
    steps = [("add", "project", "Garden Redesign"),
             ("add-mode", "agency", "--quote", "Add my consultancy as well."),
             ("add", "client", "Acme"),
             ("add", "project", "Pricing Revamp", "--in", "acme")]
    for step in steps:
        done = h.onboard(root, *step)
        assert done.returncode == 0, (step, done.stderr)
        out = json.loads(probe(root, "--json").stdout)
        assert (out["result"], out["score"], out["total"]) == ("pass", 5, 5), (step, out["answers"])
    ents = next(q for q in json.loads((root / "brain" / "probe.json").read_text())["questions"]
                if q["id"] == "entities")["expect"]
    assert {"agency", "clients/acme", "life/projects/garden-redesign"} <= set(ents)
