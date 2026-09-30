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

### Verifier signatures are automated attestations

The registered verifier key (Cyra, `F9321F92…76E8`) belongs to an automated
reviewer. By design it has no passphrase and is used by the review automation
without a human in the loop. A valid Cyra verdict attests **"the automated
review of this exact content passed"**. It does **not** mean a human approved the
change. Earlier Reid verifier keys are retired, and no Reid key is registered in
`policy.yaml`'s `verifier_keys`.

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
  cryptography. For a real boundary, run agents in the runtime's sandbox or as
  another OS user.
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
- **Codex runs Tess's gate only when it runs project hooks at all.** In an
  untrusted project, or before the operator approves the Tess hooks in `/hooks`
  (and again after an update changes their hash), Codex runs no Tess hook and only
  its own sandbox and approval settings apply. Input typed into an already-open
  shell with `write_stdin` never reaches the gate, and a hook that times out or
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
  `tessctl`, and the git hooks Tess installs) is kept in
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
  another worktree stop Tess there too.
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
  planned for 1.0.1.
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
