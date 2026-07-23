"""
Regression coverage for issue #22 (OTA upgrade regression tests) — conflict-
halts-the-update, exercised through the FULL `tessctl update` CLI pipeline
(fetch -> signature-verify -> per-file merge -> core-advance -> new-file
adoption -> render -> version-bump), not just the lower-level
`_apply_per_file_resolution` call that test_merge_engine.py already covers.

test_merge_engine.py proves the merge engine itself halts on conflict and
does not clobber the live file. test_clean_upgrade_e2e.py proves a SUCCESSFUL
`tessctl update` advances core, adopts new files, and bumps the version. This
file closes the gap between them: when the SAME full pipeline hits a
conflict, it must (a) still exit non-zero, (b) leave the conflicting file's
live content untouched, (c) release the update.lock (finally-block, not just
on the happy path), and — the part no other test asserts — (d) NOT advance
`framework.version`/`upstream_ref`, because Steps 6.5-8 (core-advance,
new-file adoption, re-pin, version bump) all run strictly AFTER
`_apply_per_file_resolution`, which raises before any of them execute.
"""

from __future__ import annotations

from conftest import make_upstream


def _scaffold_render(project):
    """cmd_update's Step 7 renders CLAUDE.md + settings.json; give it the
    minimal template + settings-core.json so render does not hard-exit.
    Neither file is tracked in tess.lock, so doctor/verify ignore them."""
    tpl = project.root / ".tess" / "core" / "templates" / "CLAUDE.md.tpl"
    tpl.parent.mkdir(parents=True, exist_ok=True)
    tpl.write_text("# Tess OS\n\nRoot: {{TESS_ROOT}}\n", encoding="utf-8")
    sc = project.root / ".tess" / "core" / "settings-core.json"
    sc.write_text('{"root": "{{TESS_ROOT}}"}\n', encoding="utf-8")


def test_cli_update_conflict_halts_full_pipeline_without_bumping_version(
    project, gpg_key, tmp_path, run_cli,
):
    # A plain core-managed file that upstream advances cleanly.
    project.add("conductor/clean.md", "clean v1\n", status="core-managed")
    # A locally-modified file where BOTH sides touch the same line -> conflict.
    base = "line-1\nline-2\nline-3\n"
    project.add("conductor/conflict.md", base, status="locally-modified")
    project.write_live("conductor/conflict.md", "line-1\nLOCAL-CHANGE\nline-3\n")
    _scaffold_render(project)

    up = make_upstream(
        tmp_path / "up_conflict_e2e", gpg_key, "v2.1.0", sign="signed",
        core_files={
            ".tess/core/conductor/clean.md": "clean v2 upstream\n",
            ".tess/core/conductor/conflict.md": "line-1\nUPSTREAM-CHANGE\nline-3\n",
        },
        lock_files={
            ".tess/core/conductor/clean.md":
                {"status": "core-managed", "tier": "normal", "live_path": "conductor/clean.md"},
            ".tess/core/conductor/conflict.md":
                {"status": "locally-modified", "tier": "normal", "live_path": "conductor/conflict.md"},
        },
    )
    project.framework["upstream"] = str(up)
    project.framework["upstream_ref"] = "v2.0.0"
    project.framework["trusted_key_fingerprint"] = gpg_key.fpr
    project.write()

    r = run_cli(project.root, "update", "--ref", "v2.1.0")

    # (a) non-zero exit — the update is BLOCKED, not silently partial.
    assert r.returncode == 1, f"expected the conflict to halt the update:\n{r.stdout}\n{r.stderr}"
    assert "CONFLICT" in r.stdout
    assert "conflict.md" in r.stdout

    # (b) the operator's conflicting version is untouched, byte-for-byte.
    assert project.read_live("conductor/conflict.md") == "line-1\nLOCAL-CHANGE\nline-3\n"

    # Documented, intentional behavior (matches test_merge_engine.py's
    # test_conflict_does_not_touch_other_clean_files at the lower level): a
    # non-conflicting file in the SAME batch is still fast-forwarded before
    # the run halts on the conflicting one.
    assert project.read_live("conductor/clean.md") == "clean v2 upstream\n"

    # (c) update.lock released even on a halted run (the `finally:` block in
    # cmd_update covers both the success and the sys.exit(1) conflict path).
    assert not (project.root / ".tess" / "update.lock").exists()

    # (d) framework.version / upstream_ref must NOT advance — Steps 6.5-8
    # (core-advance, new-file adoption, re-pin, version bump) live strictly
    # after `_apply_per_file_resolution` in cmd_update and must never run
    # when it raises on conflict.
    lock = project.lock()
    assert lock["framework"]["version"] == "2.0.0"
    assert lock["framework"]["upstream_ref"] == "v2.0.0"
    # ...and the core-managed clean file's OWN base_sha must not have been
    # re-pinned either — re-pinning it would silently mask the fact that
    # core never actually advanced for the still-conflicted release.
    assert lock["files"][".tess/core/conductor/clean.md"]["base_sha"] == project.mod.sha256_bytes(b"clean v1\n")

    # Conflict markers parked for manual resolution — not a silent overwrite.
    conflict_file = project.root / ".tess" / "conflicts" / "conductor_conflict.md"
    assert conflict_file.exists()
    parked = conflict_file.read_text()
    assert "LOCAL-CHANGE" in parked and "UPSTREAM-CHANGE" in parked
    assert "<<<<<<<" in parked
