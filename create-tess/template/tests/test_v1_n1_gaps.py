"""
v1.0.x QA (Quinn, release/v1.0 @ aa69307): three correctness gaps in the F6 /
N1 "slash-free run-time part" rule, as tests that fail on aa69307 and pass
after the fix. The harness (fixture, decisions, ALLOW/ASK/DENY) is the one in
tests/test_v1_n1_n3.py.

GAP-1 (present before N1)  A symlink under the fixed folder (planted by the
             command, or already on disk) redirected a write whose run-time
             part holds no "/": `ln -s "$PWD" /var/tmp/b-0 && echo x >
             "/var/tmp/b-$?/.claude/settings.local.json"` was allowed, while
             the literal `/var/tmp/b-0/...` was resolved and denied. Now the
             fast path resolves those links first. `.claude/settings.local.json`
             is also an anchored file now (see test_v1_local_settings_anchor.py).
GAP-2        `_rebound("PATH")` compared PATH from the environment with "all
             digits", so it was always true and every `$(date +%s)`, `$(id -u)`,
             `$(whoami)` ... after a safe prefix asked, against SECURITY.md.
GAP-3        Any builtin that binds a variable counted as rebinding $RANDOM when
             run-time text appeared ANYWHERE in its argument (a value, a
             redirection), not only in a name position.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os

import pytest

from test_v1_n1_n3 import ALLOW, ASK, DENY, REPO, T, _all, _env, proj  # noqa: F401 — fixtures


# ---------------------------------------------------------------- GAP-1 (BLOCKS)
def _planted_link(proj, name="b-0", folder="slashfree-links", target=None):  # noqa: F811
    """A /var/tmp-style folder outside the project holding a symlink INTO it."""
    root = proj[0]
    outside = root.parent / folder
    outside.mkdir(exist_ok=True)
    link = outside / name
    if not os.path.lexists(str(link)):
        os.symlink(str(target or root), str(link))
    return str(outside)


def test_slashfree_runtime_part_does_not_skip_a_symlink_in_the_same_command(proj):  # noqa: F811
    # ln plants b-0; $? is 0 after the successful ln, so b-$? == b-0 -> project.
    root = proj[0]
    outside = root.parent / "sf-same"
    outside.mkdir(exist_ok=True)
    cmd = (f'ln -s "{root}" "{outside}/b-0" && '
           f'echo \'{{"disableAllHooks":true}}\' > "{outside}/b-$?/.claude/settings.local.json"')
    assert _all(proj, cmd) == ASK, cmd


def test_slashfree_runtime_part_does_not_skip_an_on_disk_symlink(proj):  # noqa: F811
    outside = _planted_link(proj, "b-0")
    # $? is 0 after `true`; b-$? resolves through the on-disk link into the project.
    cmd = f'true; rm -rf "{outside}/b-$?/CLAUDE.md"'
    assert _all(proj, cmd) == ASK, cmd
    # the literal spelling of the identical path already denies — they must agree
    assert _all(proj, f'rm -rf "{outside}/b-0/CLAUDE.md"') == DENY


def test_a_link_deeper_than_the_run_time_part_is_resolved_too(proj):  # noqa: F811
    root = proj[0]
    outside = root.parent / "sf-deep"
    (outside / "b-0").mkdir(parents=True, exist_ok=True)
    if not os.path.lexists(str(outside / "b-0" / "sub")):
        os.symlink(str(root), str(outside / "b-0" / "sub"))
    cmd = f'true; rm -rf "{outside}/b-$?/sub/CLAUDE.md"'
    assert _all(proj, cmd) == ASK, cmd
    assert _all(proj, f'rm -rf "{outside}/b-0/sub/CLAUDE.md"') == DENY


def test_a_link_to_home_or_a_control_file_counts_too(proj):  # noqa: F811
    home = proj[1]
    (home / ".claude").mkdir(exist_ok=True)
    outside = _planted_link(proj, "h-0", folder="sf-home", target=home)
    # through a link to the home folder onto ~/.claude (a control folder)
    assert _all(proj, f'rm -rf "{outside}/h-0/.claude"') == DENY
    assert _all(proj, f'true; rm -rf "{outside}/h-$?/.claude"') == ASK
    # a link straight onto a control folder
    outside = _planted_link(proj, "c-0", folder="sf-ctl", target=home / ".claude")
    assert _all(proj, f'true; echo x > "{outside}/c-$?/settings.json"') == ASK


def test_a_link_whose_own_path_is_only_known_at_run_time_asks(proj):  # noqa: F811
    root = proj[0]
    outside = root.parent / "sf-rt"
    outside.mkdir(exist_ok=True)
    cmd = f'ln -s "{root}" "{outside}/b-$$" && rm -rf "{outside}/b-$$/CLAUDE.md"'
    assert _all(proj, cmd) == ASK, cmd


def test_a_folder_with_no_redirecting_link_keeps_the_fast_path(proj):  # noqa: F811
    root = proj[0]
    outside = root.parent / "sf-clean"
    (outside / "b-0").mkdir(parents=True, exist_ok=True)
    elsewhere = root.parent / "sf-elsewhere"
    elsewhere.mkdir(exist_ok=True)
    if not os.path.lexists(str(outside / "b-1")):
        os.symlink(str(elsewhere), str(outside / "b-1"))  # a link, but not into the project
    for cmd in (f'true; rm -rf "{outside}/b-$?/x"', f'rm -rf "{outside}/b-$RANDOM"',
                f'ln -s "{elsewhere}" "{outside}/b-2" && rm -rf "{outside}/b-$?/x"'):
        assert _all(proj, cmd) == ALLOW, cmd


def test_settings_local_json_is_anchored():
    # disableAllHooks in settings.local.json disables the gate and is only caught
    # by a human `tessctl doctor` run unless it is anchored like settings.json.
    import sys
    sys.dont_write_bytecode = True
    loader = importlib.machinery.SourceFileLoader("tessctl_anchor_gap1",
                                                  str(REPO / ".tess" / "bin" / "tessctl"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    assert ".claude/settings.local.json" in mod.ANCHOR_FILES


# ---------------------------------------------------------------- GAP-2 (noise)
SLASHFREE_SUBS_ALLOWED = [
    'rm -rf "/var/tmp/b-$(date +%s)"',
    'rm -rf "/var/tmp/b-$(date -u +%Y%m%dT%H%M%S)"',
    'rm -rf "/var/tmp/b-$(id -u)/CLAUDE.md"',
    'rm -rf "/var/tmp/b-$(whoami)"',
    'rm -rf "/var/tmp/b-$(hostname -s)"',
    'rm -rf "/var/tmp/b-$(uuidgen)"',
    'rm -rf "/var/tmp/b-$(git rev-parse --short HEAD)"',
]


@pytest.mark.parametrize("cmd", SLASHFREE_SUBS_ALLOWED)
def test_documented_slashfree_substitutions_are_allowed(proj, cmd):  # noqa: F811
    # SECURITY.md lists these as trusted-slash-free; _rebound("PATH") must not
    # distrust them via its environment check.
    assert _all(proj, cmd) == ALLOW, cmd


def test_a_path_change_still_distrusts_a_date_substitution(proj):  # noqa: F811
    cmd = 'export PATH="$HOME/bin:$PATH"; rm -rf "/var/tmp/b-$(date +%s)"'
    assert _all(proj, cmd) == ASK, cmd  # PATH changed -> date not trusted


# ---------------------------------------------------------------- GAP-3 (noise)
BINDER_NOISE_ALLOWED = [
    'export PATH="$HOME/bin:$PATH"; rm -rf "/var/tmp/b-$RANDOM"',
    'read -r x < "$f"; rm -rf "/var/tmp/b-$RANDOM"',
    'local x="$y"; rm -rf "/var/tmp/b-$RANDOM"',
    'export FOO="$BAR"; rm -rf "/var/tmp/b-$RANDOM"',
    'declare greeting="$msg"; rm -rf "/var/tmp/b-$RANDOM"',
]


@pytest.mark.parametrize("cmd", BINDER_NOISE_ALLOWED)
def test_a_binder_that_cannot_name_the_variable_does_not_rebind_it(proj, cmd):  # noqa: F811
    assert _all(proj, cmd) == ALLOW, cmd


BINDER_DYNAMIC_NAME_ASKED = [
    'name=RANDOM; declare $name=1; rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"',
    'name=RANDOM; printf -v $name %s x; rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"',
    'n=RANDOM; export $n=x; rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"',
    'n=RAN; read ${n}DOM < id2.txt; rm -rf "/var/tmp/b-$RANDOM/CLAUDE.md"',
    # beyond Quinn's list: a nameref turns a VALUE into a name
    'n=RAN; declare -n r=${n}DOM; unset r; read r < id2.txt' + T,
    'n=RAN; local -n r=${n}DOM; unset r; read r < id2.txt' + T,
    'n=RAN; declare -n r; r=${n}DOM; unset r; read r < id2.txt' + T,
    'o=n; n=RAN; declare -$o r=${n}DOM; unset r; read r < id2.txt' + T,
    'read -a ${n}DOM < id2.txt' + T,
    # builtins that run text as code keep the strict rule
    'eval x=$y' + T,
    'command eval x=$y' + T,
    'builtin eval x=$y' + T,
    'trap "x=$y" DEBUG' + T,
    'let x=$y' + T,
    'mapfile -C "$cb" -c 1 arr < id2.txt' + T,
]


@pytest.mark.parametrize("cmd", BINDER_DYNAMIC_NAME_ASKED)
def test_a_binder_with_a_dynamic_name_still_rebinds(proj, cmd):  # noqa: F811
    assert _all(proj, cmd) == ASK, cmd


def test_source_of_a_fixed_path_is_never_relaxed(proj):  # noqa: F811
    # rejecting noise-proposal part 2: a sourced file can rebind the variable.
    assert _all(proj, 'source ./setvars.sh; rm -rf "/var/tmp/b-$RANDOM"') == ASK
    assert _all(proj, '. ./setvars.sh; rm -rf "/var/tmp/b-$RANDOM"') == ASK
