"""`tessctl update` keeps the adopter's production paths (v1.0.0 RC phase 5).

The setup (`--prod-paths`) or a hand edit replaces the release policy's
placeholder glob `__REPLACE_ME__/prod/**` with the adopter's folders. Before
this, `update` compared the release's rules with the installed ones, saw
"no longer protects src/**" and stopped; approving it put the placeholder
back, so the ship gate reviewed no app code again.

Now `update` carries the installed glob list into the release's placeholder
rule, and only that: require_verdict, allowed_verifiers and every other byte
stay the signed release's. The installed rule must equal the release's rule
in everything but its globs; otherwise nothing is carried and the usual
rule-change approval applies. The gate recomputes the same carry from the
base commit, so it accepts exactly that edit without a verdict."""
from __future__ import annotations

import pytest
import yaml

from test_v1_gate_hardening import (  # noqa: F401 — helpers
    POL_KEY, POL_LIVE, RELEASE_POLICY, _commit, _gate_ci, _installed, _registries, _tessctl,
    _update, needs_gpg,
)

PLACEHOLDER = '        - "__REPLACE_ME__/prod/**"\n'
RULE_TAIL = ("      classification: [prod_touching, client_facing]\n"
             "      require_verdict: true\n"
             "      allowed_verifiers: [Reid, Quinn]\n")
RULE_ID = "example-prod-service-placeholder"


@pytest.fixture(scope="module")
def wizard(engine):
    """The release policy after the setup's registry reset."""
    return engine._policy_reset_registries_text(RELEASE_POLICY)


def _with_globs(text: str, *globs: str) -> str:
    """What create-tess writes for `--prod-paths`."""
    assert text.count(PLACEHOLDER) == 1
    return text.replace(PLACEHOLDER, "".join(f'        - "{g}"\n' for g in globs))


def _edit_rule_tail(text: str, new_tail: str) -> str:
    """Change the fields after the production rule's globs (that rule only)."""
    start = text.index(f"- id: {RULE_ID}\n")
    at = text.index(RULE_TAIL, start)
    return text[:at] + new_tail + text[at + len(RULE_TAIL):]


def _prod_rule(text: str) -> dict:
    rules = yaml.safe_load(text)["policy"]["rules"]
    return next(r for r in rules if r.get("id") == RULE_ID)


def test_the_release_rule_has_the_fields_these_tests_edit():
    pre, post = RELEASE_POLICY.split(PLACEHOLDER)
    assert post.startswith(RULE_TAIL)


# --- the carry itself --------------------------------------------------------

@pytest.mark.parametrize("globs", [["src/**"], ["src/**", "api/**"], ["infra/prod/*.tf"],
                                   [f"d{i}/**" for i in range(20)]])
def test_setup_paths_are_carried_byte_for_byte(engine, wizard, globs):
    mine = _with_globs(wizard, *globs)
    assert engine._policy_carry_prod_paths(wizard, mine) == mine
    assert engine._policy_prod_paths_to_carry(wizard, mine) == (globs, None)


def test_hand_written_paths_are_carried_in_the_setup_form(engine, wizard):
    """A hand edit in another YAML style carries the same list, written the
    way the setup writes it (so the gate's exact-form check accepts it)."""
    mine = wizard.replace('      globs:\n' + PLACEHOLDER, '      globs: [src/**, "api/**"]\n')
    assert mine != wizard
    out = engine._policy_carry_prod_paths(wizard, mine)
    assert out == _with_globs(wizard, "src/**", "api/**")
    assert engine._policy_with_prod_paths_ok(wizard, out) is True


def test_registries_and_paths_are_carried_together(engine, wizard):
    """The release ships the maintainers' verifier key; the install emptied
    the registries and set paths: update keeps both of the install's."""
    mine = _with_globs(wizard, "src/**")
    with_keys = engine._policy_carry_registries(RELEASE_POLICY, mine)
    assert engine._policy_carry_prod_paths(with_keys, mine) == mine


def test_a_release_change_elsewhere_still_carries_the_paths(engine, wizard):
    release = wizard + "# upstream note\n"
    mine = _with_globs(wizard, "src/**")
    assert engine._policy_carry_prod_paths(release, mine) == _with_globs(release, "src/**")


def test_nothing_to_carry_while_the_install_has_the_placeholder(engine, wizard):
    assert engine._policy_carry_prod_paths(wizard, wizard) == wizard
    assert engine._policy_prod_paths_to_carry(wizard, wizard) == (None, None)


@pytest.mark.parametrize("tail,label", [
    (RULE_TAIL.replace("require_verdict: true", "require_verdict: false"), "verdict off"),
    (RULE_TAIL.replace("[Reid, Quinn]", "[Reid, Quinn, Ada]"), "verifier list widened"),
    (RULE_TAIL.replace("[Reid, Quinn]", "[Quinn]"), "verifier list narrowed"),
    (RULE_TAIL.replace("[prod_touching, client_facing]", "[prod_touching]"), "classification"),
    (RULE_TAIL + "      note: mine\n", "extra field"),
], ids=["verdict-off", "verifiers-widened", "verifiers-narrowed", "classification",
        "extra-field"])
def test_an_install_rule_changed_beyond_its_globs_carries_nothing(engine, wizard, tail, label):
    """A disabled require_verdict, a widened (or any other) verifier list:
    nothing of the installed rule moves, and update names why."""
    mine = _edit_rule_tail(_with_globs(wizard, "src/**"), tail)
    assert _prod_rule(mine) != _prod_rule(_with_globs(wizard, "src/**")), label
    assert engine._policy_carry_prod_paths(wizard, mine) == wizard
    globs, why = engine._policy_prod_paths_to_carry(wizard, mine)
    assert globs is None and "differs from the release's in more than its globs" in why


def test_a_release_that_changes_the_rule_carries_nothing(engine, wizard):
    release = _edit_rule_tail(wizard, RULE_TAIL.replace("[Reid, Quinn]", "[Reid, Quinn, Cyra]"))
    mine = _with_globs(wizard, "src/**")
    assert engine._policy_carry_prod_paths(release, mine) == release


@pytest.mark.parametrize("glob", ["/etc/**", "**", "*", "../up/**", "a b/**", "src//x",
                                  '"q"/**', "__REPLACE_ME__/x/**", "src/{a,b}/**"])
def test_globs_the_setup_could_not_write_are_not_carried(engine, wizard, glob):
    pre, post = wizard.split(PLACEHOLDER)
    mine = pre + "        - " + yaml.safe_dump(glob, default_style='"').strip() + "\n" + post
    assert _prod_rule(mine)["globs"] == [glob]
    assert engine._policy_carry_prod_paths(wizard, mine) == wizard
    globs, why = engine._policy_prod_paths_to_carry(wizard, mine)
    assert globs is None and "could not have written" in why


def test_more_than_twenty_or_duplicate_globs_are_not_carried(engine, wizard):
    for globs in ([f"d{i}/**" for i in range(21)], ["src/**", "src/**"]):
        mine = _with_globs(wizard, *globs)
        assert engine._policy_carry_prod_paths(wizard, mine) == wizard


def test_a_renamed_or_missing_rule_carries_nothing(engine, wizard):
    renamed = _with_globs(wizard, "src/**").replace(f"- id: {RULE_ID}", "- id: app-code")
    assert engine._policy_carry_prod_paths(wizard, renamed) == wizard
    assert engine._policy_prod_paths_to_carry(wizard, renamed) == (None, None)


# --- what the gate accepts ---------------------------------------------------

def test_gate_accepts_the_release_with_the_bases_paths(engine, wizard):
    base = _with_globs(wizard, "src/**", "api/**")
    head = engine._policy_carry_prod_paths(
        engine._policy_carry_registries(RELEASE_POLICY, base), base)
    assert head == base
    assert engine._gate_release_policy_ok(base, head.encode(), RELEASE_POLICY.encode()) is True


def test_gate_refuses_paths_the_base_did_not_have(engine, wizard):
    base = _with_globs(wizard, "src/**")
    for head in (_with_globs(wizard, "src/**", "infra/**"), _with_globs(wizard, "lib/**")):
        assert engine._gate_release_policy_ok(base, head.encode(), RELEASE_POLICY.encode()) is False


def test_gate_refuses_the_carry_when_the_base_rule_is_weaker(engine, wizard):
    """A base whose prod rule has require_verdict off or a widened verifier
    list gets no carry, so a head that is "release + the base's globs" is
    not an accepted update policy (it needs a verdict or an approval)."""
    for tail in (RULE_TAIL.replace("require_verdict: true", "require_verdict: false"),
                 RULE_TAIL.replace("[Reid, Quinn]", "[Reid, Quinn, Ada]")):
        base = _edit_rule_tail(_with_globs(wizard, "src/**"), tail)
        head = _with_globs(wizard, "src/**")
        assert engine._gate_release_policy_ok(base, head.encode(), RELEASE_POLICY.encode()) is False


def test_gate_refuses_a_carried_policy_that_also_weakens_the_rule(engine, wizard):
    base = _with_globs(wizard, "src/**")
    for tail in (RULE_TAIL.replace("require_verdict: true", "require_verdict: false"),
                 RULE_TAIL.replace("[Reid, Quinn]", "[Reid, Quinn, Ada]")):
        head = _edit_rule_tail(base, tail)
        assert engine._gate_release_policy_ok(base, head.encode(), RELEASE_POLICY.encode()) is False


# --- a real `tessctl update`, then the gate ------------------------------------

@needs_gpg
def test_update_keeps_setup_paths_and_the_gate_accepts_it(project, gpg_key, tmp_path, run_cli,
                                                          engine, wizard):
    mine = _with_globs(wizard, "src/**", "api/**")
    base = _installed(project, gpg_key, tmp_path, run_cli, engine, installed_policy=mine)
    r = _update(project.root, run_cli)
    assert "kept your production paths" in r.stdout and "src/**, api/**" in r.stdout
    for rel in (POL_KEY, POL_LIVE):
        text = (project.root / rel).read_text(encoding="utf-8")
        assert text == mine, rel
        assert _registries(project.root, rel) == ({}, {})
        assert "__REPLACE_ME__" not in yaml.safe_dump(_prod_rule(text))
    head = _commit(project.root, "tessctl update v2.1.0")
    r, out = _gate_ci(project.root, base, head)
    assert r.returncode == 0 and out["blocked"] is False, out
    assert out["release_proof"]["status"] == "accepted"
    assert _tessctl(project.root, "verify").returncode == 0


@needs_gpg
def test_update_keeps_hand_written_paths(project, gpg_key, tmp_path, run_cli, engine, wizard):
    mine = wizard.replace('      globs:\n' + PLACEHOLDER, '      globs: [src/**]\n')
    base = _installed(project, gpg_key, tmp_path, run_cli, engine, installed_policy=mine)
    _update(project.root, run_cli)
    for rel in (POL_KEY, POL_LIVE):
        assert (project.root / rel).read_text(encoding="utf-8") == _with_globs(wizard, "src/**")
    head = _commit(project.root, "tessctl update v2.1.0")
    r, out = _gate_ci(project.root, base, head)
    assert r.returncode == 0 and out["blocked"] is False, out


@needs_gpg
@pytest.mark.parametrize("tail", [
    RULE_TAIL.replace("require_verdict: true", "require_verdict: false"),
    RULE_TAIL.replace("[Reid, Quinn]", "[Reid, Quinn, Ada]"),
], ids=["require-verdict-off", "verifiers-widened"])
def test_update_stays_strict_when_the_rule_was_changed_beyond_paths(project, gpg_key, tmp_path,
                                                                    run_cli, engine, wizard,
                                                                    tail):
    """Nothing is carried: update shows the rule change, needs a person at a
    terminal to accept it, and changes nothing without one."""
    mine = _edit_rule_tail(_with_globs(wizard, "src/**"), tail)
    _installed(project, gpg_key, tmp_path, run_cli, engine, installed_policy=mine)
    r = run_cli(project.root, "update", "--ref", "v2.1.0")
    out = r.stdout + r.stderr
    assert r.returncode != 0, out
    assert "were not carried" in out and "differs from the release's" in out
    assert "a person has to approve new safety rules" in out
    assert f"CHANGED rule '{RULE_ID}'" in out
    for rel in (POL_KEY, POL_LIVE):
        assert (project.root / rel).read_text(encoding="utf-8") == mine, rel


@needs_gpg
def test_weakening_the_carried_rule_after_update_is_blocked(project, gpg_key, tmp_path, run_cli,
                                                            engine, wizard):
    mine = _with_globs(wizard, "src/**")
    base = _installed(project, gpg_key, tmp_path, run_cli, engine, installed_policy=mine)
    _update(project.root, run_cli)
    weak = _edit_rule_tail(mine, RULE_TAIL.replace("require_verdict: true",
                                                   "require_verdict: false"))
    for rel in (POL_KEY, POL_LIVE):
        (project.root / rel).write_text(weak, encoding="utf-8")
    lock_p = project.root / ".tess" / "tess.lock"
    lock = yaml.safe_load(lock_p.read_text(encoding="utf-8"))
    lock["files"][POL_KEY]["base_sha"] = engine.sha256_bytes(weak.encode("utf-8"))
    lock_p.write_text(yaml.safe_dump(lock), encoding="utf-8")
    head = _commit(project.root, "update + turn the production rule off")
    r, out = _gate_ci(project.root, base, head)
    assert r.returncode == 1 and out["blocked"] is True, out
