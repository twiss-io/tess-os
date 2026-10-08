# Security Policy

Thank you for helping keep Tess OS and its users safe. This document explains how
to report a vulnerability responsibly and what to expect in return.

## Report privately — do not open a public issue

**Please do not report security vulnerabilities through public GitHub issues,
pull requests, or discussions.** A public report tips off attackers before a fix
is available.

Instead, report privately through one of:

- **GitHub Security Advisories (preferred)** — use the repository's
  **Security → Report a vulnerability** ("Privately report a vulnerability")
  flow, which opens a private advisory thread with the maintainers.
- **Email** — **legal@twiss.io**, if you are unable to use GitHub Security
  Advisories.

If you wish to encrypt your report, request a key in your first (low-detail)
message and we will share one.

## What to include

A good report helps us reproduce and triage quickly:

- The component affected (e.g. `tessctl` engine, the **vault** subsystem, a guard
  hook, the `create-tess` wizard, a guardrail/doctrine gate).
- The version / commit you tested against.
- Steps to reproduce, a proof-of-concept, or the conditions required.
- The impact you believe it has (what an attacker could read, write, or bypass).
- Any suggested remediation, if you have one.

## Our commitment

- We will **acknowledge** your report within a few business days.
- We will work with you to **confirm** the issue and determine its severity.
- We will keep you **informed** of remediation progress.
- We will **credit** you when the fix is published, unless you prefer to remain
  anonymous.
- We ask that you give us a **reasonable opportunity to fix** the issue before
  any public disclosure (coordinated disclosure).

## Trust model

**The release-signing key is the single root of trust, and signing a release tag
is the single human step.** Everything before a release is automated: CI, the
automated verifier verdicts, and merges to `main`. Nothing reaches users unless it
comes from a tag signed by that key.

| | |
|---|---|
| Key | Twiss Release Signing Key, fingerprint `EBEA BC61 8C11 B6A7 340A  7D16 01DD 6376 67B8 CC89` |
| Public key | [`.tess/keys/twiss-release-key.asc`](.tess/keys/twiss-release-key.asc) |
| Custody | The private key is passphrase-protected. The passphrase is stored in the maintainer's OS keychain with no pre-authorised applications, so every use needs the maintainer to approve an OS prompt on the signing machine. gpg-agent forgets it after at most 60 seconds idle (300 seconds absolute). |
| Human step | The maintainer signs the release tag (`git tag -s`) and approves the prompt. No other step needs a person. |

### What the signature gates

| Channel | Check | Runs on |
|---|---|---|
| GitHub Release (`v*` tags) | `release.yml` Gate 1: the tag must be annotated and pass `git verify-tag` against the `TESS_SIGNING_PUBKEY` secret. | GitHub Actions |
| npm `create-tess` (`create-tess-v*` tags) | `publish-npm.yml` Gate 0: annotated tag, `VALIDSIG` from the pinned fingerprint above. The job runs in the `npm-publish` environment, which only admits `create-tess-v*` tags, and npm Trusted Publishing is bound to that environment. | GitHub Actions |
| `tessctl update` / `self-update` | The tag is verified in an isolated GNUPGHOME seeded only with the pinned `framework.trusted_key_fingerprint` before any file is extracted. If no fingerprint is pinned, the update refuses unless the operator passes `--trust-on-first-use`, which records the first signer seen. New installs ship with the fingerprint pinned. | The user's machine |

Repository rulesets back this up. `v*` and `create-tess-v*` tags cannot be moved
or deleted by anyone, including admins. Only repository admins can create them.
Branches named `v<digit>…` or `create-tess-v…` cannot be created, so a branch can
never shadow a release tag.

<a id="verifier-signatures-are-automated-attestations"></a>

### Verifier signatures attest a review, and the operator signs them

The registered verifier key (Cyra, `F9321F92…76E8`) attests a review. A valid
Cyra verdict means **"the review of this exact content passed"**. It does **not**
mean a human approved the change. Earlier Reid verifier keys are retired, and no
Reid key is registered in `policy.yaml`'s `verifier_keys`.

Since the v1.0 security audit, `tessctl verdict sign` (and `tessctl gate signoff
sign` for hard-floor sign-offs) no longer signs for whoever runs it. It needs a
person at a terminal who is shown the verdict and types `sign as <name>`; the
key must be the one the committed `policy.yaml` registers for that name, kept
outside the project and protected by a passphrase (or on a hardware token); and
the passphrase gpg-agent cached is forgotten right after signing. The Cyra
reviewer role drafts the verdict; the maintainer signs it. The Cyra key was
created without a passphrase, so it needs one (`gpg --passwd`) before it can
sign again. What this does not stop is in Known limits.

### No required human PR review, by design

The `main` ruleset requires the status checks (including the App-bound
`tessctl gate ci`), strict up-to-date branches and no bypass actors. It requires
**0 approving reviews**, deliberately. Review is automated. The human control sits
at release, not at merge.

### What an attacker with repository write access can and cannot do

**Can:** open and merge pull requests to `main` that pass the required checks,
including changes to workflows. Push ordinary branches. If they also control the
review automation, produce valid Cyra verdicts. In other words, `main` can contain
unreviewed-by-a-human code. That is why `main` is not a release.

**Cannot:**
- Create, move or delete a `v*` / `create-tess-v*` tag. Creation is admin-only, and nobody can update or delete these tags.
- Publish `create-tess` to npm. That needs a job in the `npm-publish` environment, which only runs on `create-tess-v*` tags.
- Get a tag accepted by `tessctl update` on a machine that pins the release fingerprint without the release key and the maintainer's approval.
- Approve a release's safety-rule changes for an installed project. The approval in `.tess/gate/policy-approvals/<tag>.json` carries an HMAC under a per-machine operator key kept outside the repository (`~/.config/tess/operator/key`, mode 0600), bound to the project's root commit, the release tag and commit, and the old and new rule digests. A pushed, copied or hand-written approval does not verify, and the directory is itself a protected path. This does not protect against a process running as the same OS user on the operator's machine, which can read the key just as it can run `tessctl approve`. A gate running without the key (a CI runner) cannot verify any approval and blocks the rule change.

**Limits, stated plainly:**
- The build automation's GitHub credentials have **admin** rights. Someone holding those credentials can create release tags and edit workflows, so the CI gates are not the last line against them. For `tessctl update` with a pinned fingerprint, the check on the user's machine still holds, because no repository change can forge the release signature.
- GitHub Release pages and uploaded assets are not signed artifacts; the signed tag is. Verify with `git verify-tag <tag>` against the key above.
- An unpinned `tessctl` install refuses to update; with `--trust-on-first-use` it trusts the first signer it sees. Keep `framework.trusted_key_fingerprint` pinned to the fingerprint above.
- If the release key or the maintainer's machine is compromised, this model is compromised. Report suspected misuse privately (see above).
- **Multi-push policy reduction on `main` (A14, the #181 lineage) is out of scope.** Someone with write access can weaken `policy.yaml` in one merge and use the weaker policy in a later one; the gate only stops a relaxation from applying to the push that introduces it. This is accepted: `main` protections are best-effort, `main` is not a release, and users are protected by the signed release tag and the pinned key when they install or update. Reports of this pattern alone are not treated as vulnerabilities; a way to get unsigned code accepted by `tessctl update` with a pinned fingerprint is.

## How Tess OS itself is audited

Tess OS audits its own releases with the method it ships: Cloudflare's
open-source security-audit skill (`.tess/core/skills/security-audit/`, MIT,
vendored unchanged; `TESS.md` there maps its roles to Tess). The rules are in
`conductor/release-process.md`:

- **Before every release tag.** Major and minor releases get a full audit of
  the release candidate. Patch releases get an audit scoped to the diff from
  the previous release; everything outside the diff is recorded as out of
  scope, not as reviewed.
- **Each run builds on the last.** A run reads the previous run's coverage
  ledger and findings, re-checks carried findings, and turns earlier blocked,
  deferred and needs-validation items into current work.
- **What must hold to tag.** `tessctl audit validate <run-dir>` passes (both
  upstream validators accept `findings.json` and `coverage-ledger.json`); no
  confirmed critical or high finding remains; every needs-validation item is
  listed in the release notes by its fingerprint and the missing fact, without
  exploit detail.
- **Where the results go.** The run folder stays on the maintainer's machine,
  outside the repository. Release notes carry only a summary (reviewed commit,
  scope, counts per verdict and severity, validator result) and the sha256 of
  `findings.json`. Unfixed findings are handled through the private reporting
  channel above, never in public issues, PRs or commits.

What this is not: the audit is run by AI agents following a published method,
with fresh verifiers who try to disprove each finding. It is not a third-party
penetration test, and a validator pass proves the files are well formed and
the coverage ledger is consistent, not that the code is free of
vulnerabilities. The method never probes deployed systems; anything that
depends on a deployment is reported as needing validation.

## Known limits

Tess OS runs as you, on your machine. These limits are residual after the v1.0.0
security reviews; they are stated so nobody relies on a check that is not there.

- **An agent running as the same OS user as you can ultimately read your local
  keys and run arbitrary programs.** The gates deny common direct paths to the key
  directory (`~/.config/tess`: the brain key and the operator key) from the shell,
  Read/Grep/Glob, edits and (in Codex) MCP tools, and they deny the common ways to
  run hidden code. They are checks on what an agent asks to do, not an operating
  system boundary. A process running as you can read any file you can read,
  including the keys, write into Claude's and Codex's transcript folders, and fake
  a terminal for the "only at a terminal" steps (`roots add`, `sync --claude-dir`
  with another folder, `accept <version>`), which are presence checks, not
  cryptography. Every step where a person must type an answer also refuses
  when it was started inside Claude Code or Codex (`CLAUDECODE`,
  `CLAUDE_CODE_ENTRYPOINT`, `CODEX_THREAD_ID`, `CODEX_SANDBOX`,
  `CODEX_SANDBOX_NETWORK_DISABLED`), before it asks: in `tessctl`, `approve`,
  `resolve`, `override`, `reset`, `rollback`, `recruit` / `bench` / `roster
  apply`, `update` / `self-update` (`accept <version>`, `downgrade to <tag>`),
  `anchor accept`, `verdict sign`, `gate signoff sign`, `gate approve`, `lock --regen`
  (with or without `--yes`) and the `publish --force` re-seed question; in the
  brain, `roots add` and `sync --claude-dir` / `--codex-home` /
  `--gemini-home` with another folder. The `vault set` / `vault rotate` value
  prompt is not one of them: it reads a secret, not a confirmation, and the
  same value can be piped in by design, so a marker check there would stop
  nothing (an agent that sets a value already knows it; reading a value back
  is what the vault guards). A program that clears its own environment passes
  the marker check too. For a real boundary, run agents in the runtime's
  sandbox or as another OS user.
- **Signing an approval is a presence and custody check, not an OS boundary.**
  `tessctl verdict sign` and `tessctl gate signoff sign` refuse to run without a
  terminal, refuse a key with no passphrase or one that is not the registered
  key, and forget the cached passphrase after signing. A program running as you
  can still fake a terminal, or call `gpg` itself with a key it can use, and the
  gate cannot tell who produced a valid signature. The control that holds is the
  key's passphrase (or a hardware token): type it only for a signing command you
  started yourself. For a real separation, keep verifier and sign-off keys on a
  hardware token or under another OS user.
- **Sign-offs approve exact content.** A hard-floor sign-off lists every file it
  approves with its content id (`artifact_hashes`), and the gate accepts it only
  for those exact contents at the pushed commit. A later change to the same file
  needs a new sign-off.
- **The vault shows secrets only to a person, and only by reference to
  programs.** `tessctl vault get --reveal` prints a value only when both input
  and output are a terminal; `vault exec` outside a terminal refuses programs
  that print or evaluate their environment (`printenv`, `env`, a shell or
  interpreter given code on its command line), refuses variables programs run or
  load (`BASH_ENV`, `ENV`, `PROMPT_COMMAND`, `LD_PRELOAD`, …), and masks the
  exact value in the program's output. What remains: a script file or any other
  program can still send the value somewhere or print it transformed (encoded,
  split), and a process running as you can fake a terminal. On macOS the vault
  identity is stored in the keychain with no pre-authorised application, so
  every read (by `tessctl` too) shows a macOS prompt: click "Allow", never
  "Always Allow". An item created before v1.0 keeps its old, open access list:
  in Keychain Access, open `tess-vault-identity`, choose Access Control, select
  "Confirm before allowing access" and remove every listed application. Linux
  secret-service and
  the `~/.config/tess/vault/identity.age` file have no per-application control:
  any program running as you can read them.
- **Hooks read command text; they cannot see commands built at run time.** A
  script that assembles a path or a command while it runs, decodes one, reads its
  program from a file, or starts another program is judged only by what its own
  command line says. The shared-note privacy check has the same limit: it
  withholds replies for sessions whose tool calls name a private path or read
  broadly (a `cd` into the instance, a glob, a recursive search, a variable), but
  a program that reads private files by itself is not seen. The privacy check
  reads the command as the shell would split it, so unusual quoting or escaping
  (a path split across quotes, backslash-escaped characters) and a tool's own
  directory switch (`git -C`, `make -C`, `npm --prefix`, `--chdir`) can hide a
  private path from it.
- **What the gate works out from command text, and where it stops.** Since the
  v1.0 audit the gate reads a command the way the shell will: it finds the
  program behind grouping, `!`, `if`/`then`, redirections, wrappers and runners
  (`env`, `nice -n 5`, `timeout`, `xargs`, `sudo`, `uv run`...), follows `bash -c`
  strings, here-strings, here-documents and `echo ... | sh`, expands `~`, `$HOME`,
  `$PWD`, `$TMPDIR`, variables and `for` lists set in the same command, braces and
  globs, tracks `cd` through `&&`, `||`, `;`, subshells and pipes, and uses a
  Codex call's own `workdir`. Since v1.0.0 it also splits unquoted variables into
  separate words, joins the values a variable can hold after an `if`, `while`,
  `case` or `&&`/`||` branch that may not run, checks the commands inside
  `${X:-$(...)}` and `$((...))`, expands git's own arguments (`git commit $FLAGS`),
  and checks aliases and functions defined in the command where they are used,
  with the words they are given. An expansion with more than 1,024 results is
  treated as unknown, never checked in part. It stops at what only exists when
  the command runs: a program named by a variable or `$(...)`, a write target
  that is a variable set elsewhere, a git option or config key read from a file
  (`git commit $(cat flags)`), file names `xargs` reads from another program, a
  shell fed by a program such as `curl`. Those ask (Claude Code) or are refused
  (Codex, and Claude Code's no-prompt modes). Aliases and functions defined
  outside the command (a shell startup file) are not seen, and a git option only
  known at run time is asked about for `git config`, `-c` and the commands
  `--no-verify` belongs to, not for every git command. Two gaps remain: a target whose fixed part is a
  folder outside the project (`/tmp/build-$ID`) is allowed, although a value
  holding `../` could climb back into it (or, unquoted, a space could add
  another path); and a program the gate has no rules for
  (a formatter, a build tool) can still write the files its own options name.
  When `cd dir; <write>` is used and the `cd` could fail, the write is checked
  in both places; `cd dir && <write>` checks it only in `dir`. `find -delete` and
  `find -exec` are checked against the files find would match (its `-name`,
  `-path`, `-type`, `!`, `-o` and `( )` are evaluated; a test such as `-mtime` counts
  as possibly true; `-prune` stops the descent unless `-depth` or `-delete` turns
  it off), up to 20,000 entries; beyond that they ask, and so do a
  changing `find -L` / `-follow`, which follows links Tess does not walk, and a
  changing `find -files0-from`. sed and awk programs are read for the files they
  write (`w FILE`, `print > "FILE"`, `-i inplace`), and Codex patch headers are
  read the way Codex reads them (lines split on newlines, trimmed of every
  Unicode space). The whole check has a 40-second budget (inside
  the 120-second hook timeout, after up to 60 seconds of the launcher's own
  check); a call it cannot finish in time asks, or is refused in Codex.
- **The gate's fail-safe: what it cannot read, it never allows.** Since v1.0.0
  (round 3) this rule is stated once and enforced on every program the gate has
  rules for (git, gh, tessctl, the file writers and editors, find, sed, awk,
  interpreters, shells, `apply_patch`, `export`, `eval`, `trap`, `source`). The
  gate first works out the arguments the shell really hands the program: brace
  expansion makes several arguments at once (`git {-c,core.hooksPath=x,commit}`
  is `git -c core.hooksPath=x commit`), a variable set in the same command is
  replaced by each value it can hold, and `$(echo ...)` or `$(printf ...)` is
  folded only when it is one plain command (`$(echo CLAUDE.md; :)` is not). A
  word that is still only known when the command runs (a variable set
  elsewhere, `$(cat file)`, `${X#y}` and other forms Tess does not fold, a
  `<(...)` feeding the program, an expansion too large to list, a program name
  built that way) and that could change a protected decision (what is written,
  a git subcommand or option, which `tessctl` step runs, a vault use, or the code
  an interpreter or shell runs) makes the call ask in Claude Code and be refused
  in Codex and the no-prompt modes; it is never allowed. Positions that cannot
  change those decisions stay allowed: a commit message after `-m`, a branch
  name after `checkout -b`, a value after `--author=`, a quoted path whose fixed
  part is a folder outside the project (`/tmp/build-$ID`, the gap named in the
  item above), a script's own arguments, and a find test when find only prints.
  A program whose own name is only known at run time is checked as each program
  the gate stands in for it (git, gh, tessctl, find, a shell, python, a file
  writer) and asks if any of them would be stopped or if it has no arguments.
  Which positions decide is set per program family in the gate; a program the
  gate has no rules for is not covered by it (the item above).
- **Codex runs Tess's gate only when it runs project hooks at all.** In an
  untrusted project, or before the operator approves the Tess hooks in `/hooks`
  (and again after an update changes their hash), Codex runs no Tess hook and only
  its own sandbox and approval settings apply. Input typed into an already-open
  shell with `write_stdin` never reaches the gate, so in Codex the gate refuses a
  bare shell or interpreter (`bash`, `python3`), which reads its program from what
  is typed later. Since v1.0.0 (round 3) this is judged after the program and its
  options are resolved (`P=python3; "$P"`, `bash -c python3`, a function body), and
  covers options that leave a program reading the terminal (`python3 -q`, `python3
  -i script.py`, `python3 -m pdb`, `node -i`, `bash -s`, `sh -i`, `perl -d`), REPLs
  and terminal programs (`irb`, `psql`, `sqlite3 db`, an editor or pager), and an
  option the gate cannot classify, which counts as interactive. A pager that a
  program opens by itself (`git log` in a terminal) is not seen. For the same reason (Codex can start a command in a
  pseudo-terminal the hook payload does not show and type into it later), the
  gate refuses every `tessctl` step that asks the operator to type an answer
  (`approve`, `update`, `rollback`, `anchor accept`, `verdict sign`...) in Codex
  even when nothing feeds it, and `tessctl` refuses those steps when it was started
  inside a Codex or Claude Code session; run them in your own terminal. Their
  read-only forms (`status`, `verify`, `doctor`, `diff`, `anchor status`,
  `lock --check`, `update --check`) stay allowed. Codex sends shell, `exec_command` and unified-exec calls to
  the hook as `Bash` with only the command text (its documented hook schema): a
  call's own `workdir` is used when a payload carries one, and otherwise relative
  paths are judged from the session folder, so a relative write in an
  `exec_command` whose `workdir` is a protected folder is not seen by the gate (the
  git hooks and the ship gate still are). A hook that times out or
  crashes in the host fails open for that call. Details:
  [adapters/CONFORMANCE.md](adapters/CONFORMANCE.md), Codex row.
- **Tess's safety files are anchored outside the repository; the anchor is not an
  OS boundary.** The gate decides from command text, and its pins
  (`.tess/core/pinned-scripts.sha256`, `.tess/tess.lock`) live in the working tree
  they check, so git routes the gate did not list (`git rebase --onto <older>
  HEAD`, `git replace` then a restore from HEAD, `git fetch --update-head-ok`,
  `git bisect`, `git archive | tar -x`, a sparse checkout that deletes the hook
  configuration) could once put an older or stubbed gate in place WITH valid
  pins. Since v1.0.0 the sha256 of every enforcement file (the hook scripts and
  launcher, `.claude/settings.json`, `.codex/config.toml`, `.codex/rules/tess.rules`,
  both copies of `policy.yaml`, the pins, the enforcement fields of `tess.lock`,
  `tessctl`, `tess.manifest.json`, and the git hooks Tess installs) is kept in
  `~/.config/tess/projects/<project id>/anchor.json` under the home directory in
  your OS user record, with a copy of each approved file beside it. It is written
  only by the installer (after `tessctl verify` passes), by `tessctl update` /
  `self-update` after a verified signed release (they refuse to run while the
  files differ), and by `tessctl anchor accept` (a person at a real terminal,
  shown the diff, typing `accept safety changes`). Before any hook runs, the
  launcher compares the files with the anchor; on any difference, a missing file,
  or a missing anchor where one was recorded, Tess's gate **stops every tool call**
  with one plain message, the other hooks are skipped with a warning, and the git
  pre-commit / pre-push hooks refuse. `tessctl restore` puts the approved copies
  back; `tessctl doctor` / `verify` / `anchor status` and `scripts/tess
  hooks-status` report the difference. The gate also refuses the routes above
  directly (defence in depth), and denies writes, not only reads, under
  `~/.config/tess`. What this does not stop: a process running as the same OS
  user can still rewrite the anchor itself (the gate refuses that to the agent's
  tools, but a program built at run time is not seen), so the anchor turns a
  silent rollback into a loud, fail-closed stop; it is not an operating-system
  boundary. A checkout that was never anchored gets none of this: installs made
  before v1.0.0 stay unanchored until a `tessctl update` or `self-update` run by
  a v1.0.0-or-later `tessctl` records one (an older engine's update does not
  know about the anchor), or until the operator runs `tessctl anchor init`,
  which records only when `tessctl verify` passes; and a plain `git clone` of the source repository is not anchored
  unless someone runs `anchor init` in it. `tessctl anchor status` says `anchor: none` for
  such a checkout, and the gate's own route checks are then the only guard.
  Maintainers who edit enforcement files on purpose (or run `tessctl
  verdict keygen`, `approve`, `vault init` or `gate install-hooks`, which change
  anchored files) confirm the change with `tessctl anchor accept`. A git worktree
  of an anchored project shares its anchor, so enforcement files that differ in
  another worktree stop Tess there too. Hiding the anchor store is a stop as
  well (v1.0.0 audit): the first hook that finds an anchor writes this
  checkout's path key into `.git/info/tess-anchored` (a path the gate
  write-protects, which no checkout, reset or rebase touches), and a listed
  checkout whose anchor is gone, or whose `~/.config` cannot be read, stops
  every tool call with a message saying to put the folder back or run
  `tessctl anchor accept`. `tessctl doctor` and `anchor status` read only the
  store, so in that case they say `anchor: none` while the hooks stop. A
  process running as you that deletes both the store and that file (outside
  the agent's gated tools) turns the stop off, as before.
- **`tess.manifest.json` is security configuration.** Its `owned_globs`,
  `never_touch` and `render_targets.enabled` decide what `tessctl` may write,
  what `doctor`, `verify` and `update` inspect, and what the publish-clean
  guard lets through, so an edit can hide drift in a Tess file, drop a
  runtime's files from every check, or let `kb/` notes through (v1.0 final
  review round 3). The gate denies agent edits of the file, the
  security-tier policy rule and CODEOWNERS name it (a pushed change to it needs
  a covering verdict at the ship gate, like any security-tier path, or your own
  `tessctl gate approve` for a push from your computer; see the next item), and
  the anchor records it. To change it yourself: edit it in your own editor, then
  run `tessctl anchor accept` in your own terminal (until you do, Tess stops,
  as for any changed safety file; `tessctl restore` puts the approved copy
  back). Editing the manifest never stops Tess from putting its own safety
  files back: `restore` puts back every security-tier file (the hooks, both
  `policy.yaml` copies, the security doctrine) whatever `owned_globs` says,
  and exits non-zero, naming the file, when it cannot put one back. `doctor`, `verify` and `lock --check` keep checking the
  Claude Code and Codex enforcement files Tess rendered here even when
  `render_targets.enabled` leaves that runtime out; a file Tess never rendered
  (your own Codex config in a project that never enabled Codex) is left alone.
  The only automated writer is a verified `tessctl update`, which adds
  the paths the signed release newly owns and records exactly those bytes as
  approved; the ship gate accepts that manifest change only when it is that
  adoption recomputed from the proven release's own manifest. An install whose
  anchor predates this has the manifest recorded, as it is then, by its next
  verified update (or by `tessctl anchor accept`).
- **The learning loop authenticates where your words came from; it cannot see
  who typed them.** A line counts as your own words only when a hook, running
  outside the agent's sandbox, took it from the runtime's own transcript store
  (`~/.claude/projects`, `$CODEX_HOME/sessions`, `~/.gemini/tmp`) and signed it
  into the ledger under `~/.config/tess/brain/`. `sync --transcript` accepts
  only files inside that store; `--claude-dir`, `--codex-home` and
  `--gemini-home` with any other folder need you at a terminal typing yes. A
  shell that cannot write the ledger (the Codex sandbox) can read the brain key
  but never mints evidence: captured turns, journal lines and accepted-record
  seals are never taken from the in-repo outbox, a sync there journals nothing
  (the next hook does), and a decision it records waits as
  pending-verification until the next hook re-checks it. `claude -p`, the
  Agent SDK, `codex exec` (and Codex as an MCP server or sub-agent), and a
  runtime started from inside another agent session (seen in the hook's
  process ancestry) are automation: their prompts are journaled as
  `automation` and never count as yours. Limits: an agent running as you
  OUTSIDE a sandbox can still read the key and write the ledger or the
  runtime's transcript folders (the first bullet above); a nested run whose
  process tree hides its parent session (for example one started through a
  detached service) and a Gemini CLI headless run are not recognised as
  automation. Record files (`brain/**/[DPCFL]-*.md`) are sealed in the same
  ledger each time the tool writes them; a record whose file does not match
  its seal (planted, hand-edited, or pulled from another machine, which has
  its own ledger) is treated as awaiting your review, never as accepted,
  confirmed or learned, until you confirm it here. On the first run after an
  upgrade the records already in the folder are sealed once as they are. A
  seal counts only while the file still says the status it was sealed with,
  and a seal the sandbox queued (even after a hook moves it into the ledger)
  never vouches for an accepted, active or confirmed record: a record the
  sandbox wrote is accepted by the next hook only by being rewritten from its
  verified quote, and a pending record nothing vouches for goes straight to
  your review.
- **The in-repo launcher and hook configuration are protected by the gate's route
  rules, not by the anchor.** The anchor check runs inside
  `.claude/hooks/run-pinned.py`, which lives in the working tree, and the hook
  commands that start it live in `.claude/settings*.json` and `.codex/**`. A git
  route that replaces the launcher with an older or stubbed copy, or points the
  hook commands at something else, skips the anchor check entirely, so the
  anchor cannot catch it. What stops those routes is the gate: writes to
  `.claude/hooks/**`, `.claude/settings*.json` and `.codex/**` are denied, and
  `git merge`, `rebase`, `cherry-pick`, `revert`, `am`, `checkout`, `switch`,
  `reset` and `pull` that would change them relative to HEAD are refused (a
  patch naming them) or need the operator (Claude Code asks; Codex, which cannot
  ask, denies). `git pull` is judged without fetching:
  a pull from this repository (`git pull . <branch>`, or an upstream whose remote
  is `.`) is checked against the exact commit it brings in; a pull from a
  remote cannot be known before its fetch, so it asks (Claude Code) or is denied
  (Codex), and `git fetch` followed by `git merge` or `git rebase` is the checked
  path. A command the gate cannot see (a program that runs git itself, or a
  change made outside the agent) can still replace the launcher. A user-level
  launcher outside the repository, registered in the user-level Claude Code and
  Codex settings so that it runs the anchor check before any in-repo file, is
  planned for 1.0.1. Git's own hooks are the other half: the launcher stops every
  Tess hook while git's effective `core.hooksPath` (any config scope, or set
  through `GIT_CONFIG_*`) points anywhere but this repository's own `.git/hooks`,
  and `scripts/tess hooks-status` and `tessctl doctor` say so with the line that
  puts it back. In a project with a `.git`, git that cannot be run or queried
  (not on the hooks' PATH, an error starting it, a timeout, an unexpected exit)
  is a stop too, never a pass, and so is a git config file that exists but
  cannot be read (git skips it silently, so a `core.hooksPath` inside it would
  be invisible); only a project with no `.git` is exempt. `tessctl doctor`
  reports this, and a changed anchor, also when it is asked about one path.
- **The gate judges paths by the file they name, and some control files live
  outside the project.** Since the v1.0 security audit the gate decides whether
  a path is protected (or is the key directory) by file identity: a case
  variant on macOS or Windows (`/users/me/PROJ/.CLAUDE/settings.json`,
  `~/.CONFIG/./TESS`), a `..` or symlinked spelling, and a move of a directory
  above the key directory (`mv ~/.config ~/cfg`) all count. It also refuses agent
  writes to files outside the project that switch Tess's enforcement off for
  every repository: `~/.gitconfig`, `$XDG_CONFIG_HOME/git/config` (and
  `~/.config/git/config`), a system `etc/gitconfig`, any file those or the
  project's `.git/config` include (one level), the user-level Claude Code
  settings (`~/.claude/settings*.json`, `~/.claude.json`) and the Codex user
  settings (`~/.codex/config.toml`, `hooks.json`, `rules/`). Set an ordinary git
  option with `git config --global <key> <value>` (keys that switch off hooks or
  run commands are refused), and edit your user-level Claude Code or Codex
  settings yourself. What this does not cover: an include chain deeper than one
  level, a hard link to a protected file made outside the agent, shell startup
  files (`~/.zshrc` and similar, which could export a git setting to later
  terminals), and a path alias a program creates while it runs.
- **Some approvals cannot be shown to you, so they are refused.** A Tess "ask"
  (force push, remote change, a merge that changes safety files, a visibility
  change) needs a person. Codex cannot ask, and Claude Code's `auto` mode can
  settle a permission prompt with its own classifier, so in both (and in
  `bypassPermissions` / `dontAsk`) the gate denies instead and says how to run
  the command yourself; switch back to default mode to be asked. The `tessctl`
  steps that record Tess's safety files as approved or change their recorded
  state (`update`, `self-update`, `approve`, `anchor`, `override`, `reset`,
  `resolve`, `rollback`, `restore --force`, `publish --force`, `capture --auto`,
  `lock --regen`, `recruit`, `bench`, `roster apply`), signing a verdict or a
  sign-off (`verdict sign`, `gate signoff sign`), and approving your own push
  (`gate approve`), are the operator's: the gate
  refuses an agent that feeds them input or fakes a terminal for them (and, in
  Codex, refuses them outright; see the Codex item above).
- **Vault values stay out of agent sessions, for the commands the gate can
  see.** The gate refuses `tessctl vault get --reveal` (and `--force`) and
  `tessctl vault exec` into a program that prints what it is given (`printenv`,
  `env`, `echo`, `cat`, a shell, an interpreter running inline code), or with
  `--as` naming a variable programs read as a file, command or setting
  (`BASH_ENV`, `PATH`, `NODE_OPTIONS`, ...). `tessctl vault exec --ref <ref> --
  <tool>` into a real tool, or a script, stays allowed; a script the agent wrote
  can still print the value (a program built at run time, the limit above).
- **Security-tier lifecycle steps are presence checks, and snapshots are not
  signed.** Every `tessctl` command that makes a security-tier file's content
  accepted, or restores one, needs a person at a real terminal who types a
  confirmation, exactly like `approve`: `approve` itself (it shows the sha256
  and diff of the exact set-aside bytes, checks them against the digest capture
  recorded in `tess.lock`, re-checks them after you type, and writes that same
  buffer), `resolve` (every mode), `override`, `reset` when it would re-pin a
  changed core file, `recruit` / `bench` / `roster apply` of a security-tier
  entry, `rollback` that changes `tess.lock` or a safety file,
  `update --allow-downgrade`, and `lock --regen` without `--yes` (type
  `re-baseline tess.lock`). `lock --regen` refuses inside Claude Code or Codex
  with or without `--yes`; outside them, `--yes` stays the non-interactive
  form maintainers and CI use (`conductor/release-process.md`), so a program
  that clears its own environment can still re-pin (the anchor then reports
  the changed pins). `publish --force` asks its re-seed question only at a
  real terminal outside an assistant session. Like `approve`, these are presence checks, not
  cryptography: a process that fakes a terminal can pass them. Rollback
  snapshots in `.tess/snapshots` are ordinary project files and carry no
  signature; only the automatic rollback inside a failed `tessctl update`
  trusts one (the snapshot that same run wrote, byte for byte). A snapshot
  restored by `tessctl rollback` is limited to files a tessctl command
  snapshots (never `.git`, never a link out of the project) and is listed for
  the person to confirm before any safety file changes, but the confirmation
  cannot tell a planted snapshot from a real one: confirm only a rollback you
  expect. During `tessctl update` a staged file is checked right before each
  read, but the renderer then reads it by path, so a change made in that
  instant and undone before the next check would not be seen; the next check
  catches any change that persists.
- **Approving your own change is local to your computer.** A fresh install has
  no verifier key, and Tess OS never creates one for it. For a deliberate change
  of your own to a protected file, `tessctl gate approve` (run in your own
  terminal; refused inside Claude Code and Codex and without a real terminal)
  shows the changed protected files and their diff and, when you type `approve
  these changes`, records an approval of exactly that content (each file's git
  blob id), HMAC-signed with the per-machine operator key
  (`~/.config/tess/operator/key`) and stored outside the repository. The
  pre-push gate on that computer accepts exactly that content; any later edit
  needs a new approval, hard-floor rules are never cleared this way, and a
  record that does not verify, or names another project, is ignored. Limits:
  it is a presence check plus a local key, not a verifier signature. A gate
  run anywhere the key is absent (`tessctl gate ci` on a CI runner) cannot
  verify it and still blocks the change, and a program running as you can read
  the key and fake a terminal, as for every presence step above.
- **The hooks heartbeat is a detection aid, not proof.** SessionStart and
  UserPromptSubmit write `.tess/state/hooks-alive.json`, and `python3 scripts/tess
  hooks-status` reads it to say whether the hooks ran in this session. It is an
  ordinary file an agent could write. `hooks-status` therefore also reports OFF
  when the runtime's hook configuration is missing or no longer runs the gate, or
  when the safety files differ from the anchor; a deleted `.claude/settings.json`
  or `.codex/config.toml` means the next session loads no Tess hook at all, which
  `tessctl doctor` / `verify` also report as a failure.
- **The operator key and the brain key are found from your OS user record.** `tessctl`
  reads `~/.config/tess/operator/key`, and the brain reads `~/.config/tess/brain/key` and
  its per-project ledger, under the home directory in the user database; both ignore
  `$HOME` and `$XDG_CONFIG_HOME`, so a command run with those pointed elsewhere
  cannot sign or verify with a key an agent made.
- **In Claude Code, MCP tools are not routed through the Tess gate.** The base
  settings must not target MCP tools (they can be external chat channels), so an
  MCP server with filesystem access can read `~/.config/tess` in Claude Code. The
  gate denies such reads when it runs (Codex routes MCP calls through it). Do not
  give an MCP server access to your home folder.
- **Protections on the `tess-os` `main` branch are best-effort.** `main` is not a
  release. Users are protected by the signed release tag and the pinned release
  key that `tessctl update` checks on their own machine.
- **An agent on the maintainer's machine that holds an admin GitHub token can
  change the release workflows** (and anything else an admin can). The
  maintainer's mitigation is to give agents a scoped non-admin token and keep the
  admin token out of agent sessions. A changed workflow still cannot forge the
  release signature that users' machines verify.

## Scope and threat model

Tess OS is a local governance framework with a doctrine/roster scaffold,
upgrade engine, and coding-agent render targets. Claude Code is the reference
integration; Codex is a pilot and generic output is an interoperability
baseline. It is not a hosted service; it runs on your machine with the
credentials and access **you** grant it. Keep this in mind when assessing impact.

We are especially interested in reports concerning:

- **The vault (`tessctl vault`).** The vault is a **local-first, encrypted-at-rest
  secret store plus a commit/push backstop — a risk reducer, not a guarantee.**
  Its threat model is documented in `conductor/vault.md`. Reports that strengthen
  it are welcome, including:
  - Ways encrypted material (`*.age`, identities, recipients) could be exposed,
    written outside the intended paths, or logged in plaintext.
  - Ways the pre-commit / pre-push guards could be **bypassed** so a secret or
    vault blob reaches a remote, or ways they silently neuter an adopter's own
    pre-existing hooks.
  - Ways a secret reference (`vault://…`) could leak its value into argv, logs,
    environment dumps, or error output.

  Out of scope for the vault, by design: it cannot protect against a compromised
  local machine, a malicious operator, an attacker who already has your age
  identity, or secrets you grant to processes Tess OS legitimately injects them
  into. The vault is **defense-in-depth**, not a vault appliance.

- **The upgrade engine (`tessctl`).** Path-escape / write-outside-root in the
  manifest write gate, merge-base (`tess.lock`) integrity bypass, security-tier
  quarantine bypass, or a doctor/verify gate that can be fooled into reporting
  clean on tampered core.

- **Guard hooks and guardrails.** Ways the dispatch guard, the client-isolation
  guardrails, or the clarification hard floor (credentials, money movement,
  destructive production operations, external factual claims), could be bypassed.

- **Secret / client-data leakage.** Anything that causes the repository, an
  instance, or the npm package to ship a real secret or client data — this repo
  is designed to contain **zero** of either.

### Release signatures (how `tessctl update` trusts a release)

Every release tag carries two independent signatures, and both keys are pinned
in the install:

- **OpenPGP.** The annotated tag is signed with the Twiss Release Signing Key
  (`.tess/keys/twiss-release-key.asc`, fingerprint pinned in `.tess/tess.lock`
  `framework.trusted_key_fingerprint`). This is unchanged from earlier releases.
- **SSH.** The tag message also carries an OpenSSH signature (namespace
  `tess-release`) by the Twiss SSH release key
  (`.tess/keys/twiss-release-allowed-signers`, SHA256 fingerprint pinned in
  `framework.trusted_ssh_key_fingerprint`). It signs the manifest
  `tess-release-manifest/1`, `tag <name>`, `object <commit>`, `tree <tree>`.
  The verifier rebuilds that manifest from the fetched git objects, so the
  signature is bound to the exact tag name and the exact commit that
  `tessctl update` and `self-update` check out. It cannot be replayed onto
  another commit, a renamed tag or a same-named branch. It needs only
  `ssh-keygen -Y verify`, which ships with macOS, most Linux distributions
  and Windows 10+, so installs without gpg can still verify updates.

When gpg is installed, the OpenPGP signature must verify; when the SSH key is
also pinned and `ssh-keygen` is present, the SSH signature must verify too.
Without gpg, the SSH signature alone decides. A missing, malformed or
wrong-key signature fails closed before any file is written. The ship gate
applies the same rule to `.tess/release-proof.json`, reading both pins and
both public keys from the base commit, never from the candidate.

After the signature check, `tessctl update` writes `.tess/staging` from the
verified commit's git objects and keeps the sha256 of every staged file in
memory; every later read of staging in that run (the policy-rule prompt, new
file adoption, the per-file apply, the core advance, the `base_sha` re-pin) is
checked against it, and the whole staging tree is re-checked before the apply
and before the lock is saved. A staged file that changed after the check stops
the update (rolling it back if the core advance had begun), so only the signed
release's bytes are applied and anchored. `self-update` reads the new engine
from the verified commit's git object the same way.

**Adding the SSH key to an older install.** An install made before the SSH
signature existed pins only the OpenPGP key, so it needs gpg to update. A
verified update ADDS the release's SSH pin and its `twiss-release-allowed-signers`
file, and only when the release's own `tess.lock` names that key, the shipped
file is that key, and the tag being installed carries a valid SSH signature by
it (the OpenPGP signature having been checked against the install's pin first).
It never removes or changes the OpenPGP pin and never replaces an SSH pin the
install already has: changing a pinned key stays the operator's decision. The
ship gate accepts the lock change only when the added pin is the proven
release's. The same update adds to the install's `tess.manifest.json` the
`owned_globs` the signed release's own manifest lists (for example
`.codex/rules/tess.rules`), only when the glob starts with a named folder or
file inside the project (never a catch-all such as `**/**`, `*/**` or `./**`),
and never one that may overlap a `never_touch` entry of the operator's own (a
narrower file inside the new glob included). Each
added glob is recorded under `adopted_owned_globs` in the manifest, and the
write gate keeps the operator's own `never_touch` ahead of it on every concrete
path, including entries added later.

**No silent downgrade.** `update` and `self-update` refuse a release tag older
than the installed version (the newer of `framework.version` and
`framework.upstream_ref`, semver order, so `v1.0.0-rc.1` is older than
`v1.0.0`), a tag that is not a Tess OS release (`vX.Y.Z`), and a
`create-tess-v*` package tag. Going back on purpose takes `--allow-downgrade`
and typing `downgrade to <tag>` at a real terminal.

**create-tess and a git template.** The wizard installs the template bundled
in the npm package by default. An explicit `--template-source` git URL must be
`https://`, and must name a release tag (`--template-ref v1.2.3`): the wizard
fetches only that tag, verifies its OpenPGP and SSH signatures with the keys
the package ships (the bundled template's `.tess/keys` and `tess.lock` pins,
never keys from the fetched tree) by the same rule as `tessctl update`, and
checks out and runs nothing before both pass. `git://`, `ssh://` and
`user@host:path` sources are refused. A local template folder is run as
trusted code, so it is accepted only when named on the command line with
`--template-source`, not from the `TESS_TEMPLATE_SOURCE` environment variable
alone.

**The first push of a fresh install** has no base commit, so no earlier
`tess.lock` pins a key. The npm package ships the proof of the signed release
it was built from (publish-npm.yml builds it from the framework tag, which must
carry both signatures and name the published commit), and the wizard writes it
to `.tess/release-proof.json` before the first commit. For a push with no base,
the gate verifies that proof against the release fingerprints compiled into
the engine (`RELEASE_ANCHOR_OPENPGP_FP`, `RELEASE_ANCHOR_SSH_FP`, equal to the
shipped pins), never against a key the pushed tree names alone, and accepts a
protected file only if it is the signed release's file byte for byte. The
engine and key files are themselves protected files, so a tree with a changed
engine or key is refused. Two differences are allowed: both `policy.yaml`
copies with the wizard's verifier/sign-off key reset applied (it only removes
trust), and the `tess.lock` re-pin and render records that follow from it.
Limit: on the first push only the local pre-push gate and a manual
`tessctl gate ci` apply this check. The installed CI workflow takes its gate
engine from the base commit and fails closed when there is none, so the first
CI run on a brand-new repository fails; every later push is checked in CI.

Write access
to the repository is not enough to forge a release: both private keys stay
offline on the maintainer's machine, each behind a passphrase that is released
only after an interactive approval.

### Generally not in scope

- Vulnerabilities in third-party dependencies you install yourself (report those
  upstream — see `NOTICE`), unless Tess OS uses them in an unsafe way.
- Issues that require a pre-compromised host, physical access, or an actively
  malicious operator.
- Social-engineering of the operator, and prompt-injection that merely *asks* the
  agent to do something the operator could already authorize — though we **do**
  want to hear about prompt-injection that defeats a guardrail or hard floor.

## A note on doing your testing safely

Please only test against your **own** instance and your **own** credentials. Do
not attempt to access data or systems that are not yours.

---

_This policy may be updated over time. It is provided for clarity and is not legal
advice._
