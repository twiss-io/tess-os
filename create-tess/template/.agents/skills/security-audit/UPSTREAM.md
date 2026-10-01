# security-audit — upstream record

This skill is Cloudflare's open-source security-audit method, vendored into
Tess OS without changes.

| Field | Value |
|---|---|
| Upstream | https://github.com/cloudflare/security-audit-skill |
| Path in upstream | `skills/security-audit/` (plus the repository `LICENSE`) |
| Commit | `c1c8a8c1471069fb0e188eeaff69b8e8db6564a8` ("Clarify guidance and full audit modes") |
| Commit date | 2026-09-14 |
| Vendored into Tess OS | 2026-09-30, v1.0.0 |
| License | MIT, Copyright (c) 2025-2026 Cloudflare, Inc. (see `LICENSE` in this folder) |

## What is ours and what is theirs

- Every file listed in the hash block below is upstream's, byte for byte.
  Never edit one. `tests/test_security_audit_skill.py` fails if any byte
  differs from this list, and it holds its own copy of the list digest, so a
  file and this record cannot be changed together unnoticed.
- `UPSTREAM.md` (this file) and `TESS.md` (how Tess runs the skill) are Tess
  OS files, Apache-2.0 like the rest of Tess OS.
- Source of truth: `.tess/core/skills/security-audit/`. The live copies are
  rendered from it: `.claude/skills/security-audit/` (Claude Code, one
  `tess.lock` entry per file) and `.agents/skills/security-audit/` (Codex,
  written by `tessctl render --target codex`). Never edit the live copies.

## Upstream files (sha256, commit c1c8a8c)

<!-- upstream-sha256:begin -->
```
7335a95c43554eadefcf03ece639291bb0e038c398a179299e3887ffe06bd2ef  AI-AND-LLM.md
3ee4f00c6e8c9dcf6dd02dd5ac2a4ceb322e2085f3e9fbe79cf0c6330bc7ef83  ATTACK-CLASSES.md
613f6b98f86083e045525c5b60154ffdab122bac35f1e05eb17488e6e453370c  CLIENT-SIDE.md
3c80f3088be22345e07b057c056d6ed99fe2b0304f794398964f7ccd5a496ca3  CLOUD-AND-DEPLOYMENT.md
307dcb3e24d292715c4a041190e7bb135646a37eb6187619ae01d000a634a4ad  DATA-ISOLATION-AND-LIFECYCLE.md
58eae8ee0ca6a46611c501ec5a3ab47fdff88dd7db0d8d74789bbf8bb19d8cb2  DESKTOP-MOBILE-AND-LOCAL-IPC.md
71c121decea1322c47c718f6e110f1a892980bb4266bd7ac55ef043a213ade09  HUNTING.md
e598e694aa506650c7192d5ea3be0e50aca0d356ea00551c53429f0b01eb6391  LICENSE
7c8b0dccfb35315cca2455509674d49632b2fe37e1f3aac16c1a496a7e9924a7  MEMORY-SAFETY-AND-BINARY.md
8b73816fa5b3697c9c40977f0c836b40f01d6e81929ff2720fe83ce089e9a619  PROTOCOLS-RPC-AND-MESSAGING.md
02ca887aca84de8ae137f1891bd2f0a54f28d3fa6da92a27f54734382b3381a2  RECONNAISSANCE.md
6575c9de4a62255699ea052ebf9a49ebfb373a32891bcd89af6f55cc84b35519  report-schema.json
4326fab5c92a0b4c420a70196254040105cd794026562130b59bf1a6db3e4baa  RESOURCE-EXHAUSTION-AND-AVAILABILITY.md
5e3e96a1e438d8f35fef0a1e38f02d4f00e2bdf910401b7dfe00e6779c6dac85  SKILL.md
f372e919940e335468ba1ae09f99026c3986a345f7fe26f8068f132e199f52a5  SUPPLY-CHAIN-AND-RELEASE.md
2eb280bd2e33c002916f86db9b29f9edfedb6454e5db973c766290465b868ac8  validate-coverage-ledger.cjs
cfb9df26b03469a4279a70e7664a2a5434dd6f8c2c204e91f9b0aeb9dd71e648  validate-coverage-ledger.test.cjs
e85f232e36bfac0f866f244da50376692d6b45c690beadcb00608b0e6c8b5283  validate-findings.cjs
b92001117a92c4161d43777a0ba2fa182a8a4d97f2304cc8c0cee5331497b73b  validate-findings.test.cjs
b892470cb89bb31f33403e050d4bdfbe2cdaef940ade1496fa65e32b2e129449  VALIDATION-AND-REPORTING.md
4f3066dffa23c5635859187be9b96c32f2aff29a688186b91ff0c63e47d62b5c  WEB-PROTOCOL-AND-AUTH.md
```
<!-- upstream-sha256:end -->

`LICENSE` is upstream's repository-root `LICENSE`; every other file is from
`skills/security-audit/`.

## How to update to a newer upstream commit

1. Clone upstream and read the full diff since `c1c8a8c`:
   `git clone https://github.com/cloudflare/security-audit-skill && git -C security-audit-skill diff c1c8a8c <new> -- skills/security-audit LICENSE`.
   The two validators are code Tess runs with `node`
   (`tessctl audit validate`), so the change is reviewed like any other
   third-party code: Cyra reads the validator diff before it lands.
2. Copy the files from the new commit into `.tess/core/skills/security-audit/`
   unchanged (`git show <new>:<path> > <file>`, never a hand edit). Add new
   files, delete removed ones.
3. Regenerate the hash block above (`shasum -a 256` over the upstream files,
   sorted by name), update the commit, date and title in the table, and update
   `UPSTREAM_COMMIT` and `UPSTREAM_LIST_SHA256` in
   `tests/test_security_audit_skill.py`.
4. Re-pin and re-render: add a `tess.lock` entry for each new file (live path
   `.claude/skills/security-audit/<file>`), then
   `python3 .tess/bin/tessctl lock --regen --only <each changed core file>`,
   copy the files to `.claude/skills/security-audit/`, and run
   `python3 .tess/bin/tessctl render --target codex`.
5. Check `TESS.md` still matches the skill (role names, phases, output files).
6. Run the full test suite, `tessctl doctor`, `tessctl verify` and
   `tessctl lock --check`; rebuild the create-tess template last.
7. Record the update in `CHANGELOG.md` and in `NOTICE` if the copyright line
   changed.
