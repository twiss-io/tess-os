# How Tess runs the security-audit skill

Read this before you use `SKILL.md` in this folder. `SKILL.md` and its
companion files are Cloudflare's method, unchanged (see `UPSTREAM.md`). This
file only says how the method's roles and outputs map onto Tess OS. Where this
file and `SKILL.md` seem to disagree on safety, the stricter rule wins.

## When to use it

- A security question, a focused review, or a check of one finding: guidance
  mode. Use the parts of the skill that apply. Write no audit files.
- "Security audit this project", "pen-test this", a full or end-to-end
  security review, or a request for report files: full audit mode. Run all six
  phases. If you cannot tell which one the operator wants, ask one question
  first.

## Who does what

| The skill says | In Tess | Claude Code | Codex |
|---|---|---|---|
| Parent | The main Tess session. It plans, keeps the coverage ledger, and is the only writer of the shared run files. | The top-level session | The top-level session |
| `research` agent (recon mapping, Phase 5 record check) | `morwenna` (Explorer) for mapping source; `leah` (Researcher) when a fact must be checked in docs or specs | Agent tool, `subagent_type: morwenna` or `leah` | `spawn_agent` with `agent_type: "morwenna"` or `"leah"` |
| `general` agent as hunter | `cyra` (Security reviewer), one fresh instance per assignment | `subagent_type: cyra` | `agent_type: "cyra"` |
| Fresh verifier (Phase 3 candidate check, Phase 5 record check) | `reid` (source verifier) or `quinn` (runs the bounded local check). Always a fresh instance that did not hunt or propose that candidate. | `subagent_type: reid` or `quinn` | `agent_type: "reid"` or `"quinn"` |

- Every delegated agent gets its own `agents/<agent-id>/scratch/` folder under
  the run directory and writes nowhere else. Copy the skill's prompt blocks
  into the brief word for word; the six brief fields
  (`conductor/dispatch-brief.md`) wrap them, they do not replace them.
- Roles keep their own permissions. A role that cannot do what a phase needs
  (for example, no sandbox is available to run target code) reports the gap;
  it does not borrow permissions.
- Size the run with `conductor/orchestration-budget.md`: offer the `quick`
  profile for a small project, and record the agent budget in
  `run-metadata.json` as the skill describes. Spawn roles only when the
  operator asked for the full audit.
- If a runtime cannot spawn roles, do not pretend it did. Say so, and either
  run guidance mode or run the phases yourself one at a time, keeping hunter
  and verifier work apart (a verifier never re-uses its own hunter notes).

## Where the files go

- Keep the upstream default: a new folder **outside the project**,
  `~/security-audit-skill/<repo-name>/run-<N>`. Never put a run inside the
  project, `brain/`, `kb/` or any folder that is pushed to a remote. The
  skill's own rule for an in-repo folder (operator asks for it, and version
  control ignores the whole folder) still applies.
- Later runs read the previous `coverage-ledger.json` and `findings.json`
  from the earlier `run-<N>` folders; that is why they stay on the machine.

## Checking a run

`tessctl audit validate <run-dir>` runs the two upstream validators on
`findings.json` and `coverage-ledger.json` with `node`. It stops with a plain
message if `node` is missing. A pass proves the files are well formed and the
ledger is consistent, nothing more.

## What goes into the brain

After a full audit, save only a short, non-sensitive summary, with a pointer
to the run folder:

- date, repository, reviewed commit, profile, scope, `run_status`;
- counts: confirmed by severity, needs_validation, rejected;
- whether both validators passed, and the sha256 of `findings.json`;
- the local path of the run folder.

Never copy finding titles, traces, file-and-line locations, reproduction
inputs or fixes into the brain, a wiki, a chat message, an issue or any
repository that is shared or public. Those stay in the run folder until the
owner fixes them.

## Safety rules stay as written

The skill's execution-safety rules apply in full: target code runs only in an
OS-enforced sandbox with no external network, an empty allowlisted
environment with a scratch `HOME` and temp folder, a read-only target, and
low resource and time limits. A runtime's own sandbox counts only if it
enforces every one of those controls; if you are not sure, do not run the
code, and record a `needs_validation` item naming the missing control. Never
probe deployed systems, and never let target code see the operator's real
home folder, keys or `~/.config/tess`.

## After the audit

The audit does not change the target. Fixes follow Tess's own discipline
(`conductor/review-and-verification.md`): each confirmed finding gets the
smallest fix at the last trusted decision point plus a regression test, built
by `ada`, and a separate fresh verifier checks each fix.
