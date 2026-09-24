"""`tessbrain.py lint` (spec 11 + 10.7 + 9.3): integrity, reachability,
people deny-list, AGENTS budgets. Exit 1 on any error (0 with --warn-only)."""
import sys
from pathlib import Path

import pytest

from fixtures.brain_learn import fxlib

sys.path.insert(0, str(Path(fxlib.REPO) / "scripts" / "brain"))
from brainlib import records  # noqa: E402
from brainlib.config import Config  # noqa: E402


@pytest.fixture
def inst(tmp_path):
    inst = Path(fxlib.make(str(tmp_path / "fx")))
    assert fxlib.sync_fixture(inst).returncode == 0
    assert fxlib.cli(inst, "lint").returncode == 0
    return inst


def lint(inst, *extra):
    r = fxlib.cli(inst, "lint", *extra)
    return r.returncode, r.stdout


def _decision(inst, rid, **meta):
    cfg = Config(inst)
    m = {"id": rid, "type": "decision", "title": "t", "status": "accepted", "source_quote": "let's go with Postgres",
         "source_at": "2026-09-24T14:05:00+08:00", "source_ref": "brain/journal/2026/09/24/1405-claude-11111111.md#L1"}
    m.update(meta)
    rec = records.write(cfg, "decision", inst / "brain/decisions", m, {"quote": m["source_quote"]})
    fxlib.cli(inst, "index")
    return rec


def test_accepted_record_needs_quote_and_resolving_ref(inst):
    _decision(inst, "D-20260924-1405-no-quote", source_quote="")
    rc, out = lint(inst)
    assert rc == 1 and "lacks source_quote" in out
    rc, out = lint(inst, "--warn-only")
    assert rc == 0 and "lacks source_quote" in out


def test_ref_that_does_not_resolve_or_does_not_contain_the_quote(inst):
    _decision(inst, "D-20260924-1405-bad-ref", source_ref="brain/journal/2026/09/24/1405-claude-11111111.md#L99")
    _decision(inst, "D-20260924-1405-wrong-line", source_quote="let's go with Oracle")
    rc, out = lint(inst)
    assert rc == 1 and "#L99 does not resolve" in out and "does not contain the source_quote" in out


def test_unreachable_record(inst):
    cfg = Config(inst)
    m = {"id": "D-20260924-1405-orphan", "type": "decision", "title": "orphan", "status": "proposed"}
    records.write(cfg, "decision", inst / "brain/misc", m, {"quote": "q"})
    rc, out = lint(inst)
    assert rc == 1 and "brain/misc/D-20260924-1405-orphan.md: not reachable" in out


def test_people_deny_list_key_and_nric_value(inst):
    people = inst / "brain/agency/people"
    people.mkdir(parents=True)
    (people / "jo.md").write_text("---\nname: Jo\nnric: on file with HR\n---\n# Jo\n")
    rc, out = lint(inst)
    assert rc == 1 and "deny-listed person field(s): nric" in out
    (people / "jo.md").write_text("---\nname: Jo\n---\n# Jo\n\nID %s\n" % ("S" + "1234567" + "D"))
    rc, out = lint(inst)
    assert rc == 1 and "NRIC/FIN-shaped value" in out


def test_agents_chain_and_entity_budgets(inst):
    (inst / "AGENTS.md").write_text("# root\n" + ("x" * 99 + "\n") * 200)  # 20 KB
    acme = inst / "brain/clients/acme/AGENTS.md"
    acme.write_text(acme.read_text() + ("y" * 79 + "\n") * 45)  # entity now ~5.3 KB, chain > 24 KiB
    rc, out = lint(inst)
    assert rc == 1 and "AGENTS chain root->entity" in out
    (inst / "AGENTS.md").write_text("# root\n")
    acme.write_text("\n" * 81 + acme.read_text())
    rc, out = lint(inst)
    assert rc == 1 and "START HERE' is not within the first 80 lines" in out
    acme.write_text(acme.read_text().lstrip("\n") + ("z" * 99 + "\n") * 20)
    rc, out = lint(inst)
    assert rc == 1 and "entity AGENTS.md over budget" in out


def _validate(obj, schema):
    """Tiny validator for the subset the brain schemas use (required, const, enum, pattern, types)."""
    import re as _re
    errs = [k for k in schema.get("required", []) if k not in obj]
    for k, rule in schema.get("properties", {}).items():
        if k not in obj:
            continue
        v = obj[k]
        if "const" in rule and v != rule["const"]:
            errs.append("%s const" % k)
        if "enum" in rule and v not in rule["enum"]:
            errs.append("%s=%r not in enum" % (k, v))
        if "pattern" in rule and isinstance(v, str) and not _re.search(rule["pattern"], v):
            errs.append("%s pattern" % k)
        if rule.get("type") == "boolean" and not isinstance(v, bool):
            errs.append("%s type" % k)
    return errs


def test_records_journal_and_candidates_match_the_schemas(inst):
    import json as _json
    from brainlib import frontmatter
    sdir = Path(fxlib.REPO) / "scripts/brain/schemas"
    load = lambda n: _json.loads((sdir / n).read_text())
    dec, rec, jour, cand = (load("decision.schema.json"), load("record.schema.json"),
                            load("journal-session.schema.json"), load("candidate.schema.json"))
    seen = 0
    for p in (inst / "brain").rglob("[DPCFL]-2*.md"):
        meta = frontmatter.read(p)[0]
        assert _validate(meta, dec if p.name.startswith("D-") else rec) == [], p.name
        seen += 1
    for p in (inst / "brain/journal").glob("*/*/*/*.md"):
        assert _validate(frontmatter.read(p)[0], jour) == [], p.name
        seen += 1
    for p in (inst / "brain/inbox").rglob("C-*.json"):
        assert _validate(_json.loads(p.read_text()), cand) == [], p.name
        seen += 1
    assert seen >= 10
