# How the Tess brain learns

Every conversation is noted. After every exchange the brain can be a little
smarter: it records preferences, corrections, facts, decisions and open loops.
It never writes something the operator did not say. This page describes the
mechanism: `scripts/brain/tessbrain.py` plus the library in
`scripts/brain/brainlib/`. The tools use only the Python standard library, run
on Python 3.9 or later, and make no network calls.

Which runtime captures what, and how reliably, is in [RUNTIMES.md](RUNTIMES.md).

## Pipeline

| Stage | What happens | Command | Label |
|---|---|---|---|
| 1. Capture | The runtime writes its own transcript. In Claude Code, the UserPromptSubmit hook also appends the redacted prompt to `.tess/state/brain/turns.jsonl` | runtime, `hook prompt` | M / M/T / M/S |
| 2. Journal | A deterministic session file is written, with redaction | `sync` | M |
| 3. Cue pass | Explicit first-person patterns on a principal's lines become candidates | `sync` | M |
| 4. Distill | The model proposes implicit candidates, each with an exact quote and a line reference | skill `brain-distill` then `inbox add` | I (nudged) |
| 5. Verify | Rules V1-V9 run on every candidate, whoever proposed it | automatic | M |
| 6. Promote | Append-only records, supersede links, and a line in `learned.md` | automatic | M |
| 7. Index | Generated registers, START HERE blocks, `profile.md`, `open-loops.md`, the journal indexes; caps enforced | `index` (also run by `sync`) | M |
| 8. Review | The operator approves, rejects, corrects or retracts, in their own words | skill `brain-review` | operator |

**Labels:** M = mechanical; M/T = mechanical after the runtime's trust step;
M/S = mechanical, by a transcript sweep; I = depends on the model following
an instruction.

## Principals and speakers

`brain/brain.json` lists the **principals**: the people whose words count as
decisions. Each principal has a `slug`, `decides`, `scope` (globs relative to
`brain/`), `aliases` (other ids for `journal note --speaker`), `git_emails` and
`journal_consent`.

The speaker of each human line is resolved like this:

- **Typed in this machine's runtime session:** the principal whose
  `git_emails` contains this clone's `git config user.email`. If no principal
  lists any git email (a fresh install), the operator. If emails are listed but
  none match, the words are omitted rather than credited to the wrong person,
  and `status` says so.
- **Another principal:** their own clone (their `git_emails`), or
  `tessbrain.py journal note --speaker <slug>`, which is held for review. A
  message a plugin injects into the session (a `<channel>` wrapper) is never
  journaled: the base harness attributes no external channel.
- **Anyone else:** written as `[non-principal <id> omitted: no consent]`.
  Consent needs an explicit `journal_consent` of `shared` (or `yes`).

## The journal (deterministic, redacted, one file per session)

**Path:** `brain/journal/YYYY/MM/DD/HHMM-<runtime>-<sid8>.md`, keyed on the
session start in the operator's timezone. Past 256 KB the session continues
in a `-2` file.

**Front matter:** `schema, type: journal-session, runtime, runtime_version,
session_id, part, source_path (`<runtime>-transcripts/<file name>`), source_sha256, started_at,
updated_at, cwd (relative to the instance root), git_branch, git_head, entities, external_context, redactions,
speakers, turns`. Schema: `scripts/brain/schemas/journal-session.schema.json`.

**Body:**

```
<!-- tess:session runtime=claude id=<session id> through=<last transcript line> -->
## Messages
[L1 14:05 <slug> cli] the principal's words, verbatim and redacted
[L2 14:10 <slug> note] ...
## Replies
[R1 14:05 assistant reply] the final assistant text after L1, at most 1,200 characters [... see transcript]
## Heuristic flags
- L1 decision: "..."
## Files touched
```

`R<k>` is the reply that followed `L<k>`, so the order of a conversation can be
reconstructed from the file. The journal leaves out tool input and output,
system reminders, injected `AGENTS.md`/`CLAUDE.md` text and command output.

**Append-only.** A cursor in `.tess/state/brain/cursors.json` (with the
`through=` marker as a fallback) means a re-run with no new records leaves
every file byte-identical. New records only add lines, and labels never move.
No machine-local path is committed: `cwd` and touched files are relative to
the instance root. A line omitted as non-principal (for example while this
machine's `git user.email` matches no principal) is remembered in the cursor
and journaled at the next sync once the speaker resolves; it is not lost.

**Policy** (`capture.journal` in brain.json): `commit-redacted` (default for
personal and agency) commits the file; `stub-only` (default for organisation)
commits the front matter and flags and keeps the bodies in
`.tess/state/brain/journal/`; `local` commits nothing; `off` keeps no journal.

Generated indexes (`journal/INDEX.md` months, `YYYY/MM/INDEX.md` days,
`YYYY/MM/YYYY-MM-DD.md` sessions) make every session reachable from START HERE.

## Redaction (before any write)

Redaction runs before anything is written to the journal, `turns.jsonl`, a
hand-written note, an inbox candidate or a record. Each match becomes
`<REDACTED:type>`: private-key blocks; AWS `AKIA`/`ASIA` keys; GitHub
`ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`/`github_pat_` tokens; `sk-`, `sk-proj-` and
`sk-ant-` keys; Google `AIza` keys; Slack `xox[abprs]-` tokens; Stripe
`sk_live_`/`rk_live_` keys; JWTs; chat-bot tokens (`<8-10 digits>:<35 chars>`);
env and config style credentials: any key containing `password`, `passwd`,
`pwd`, `secret`, `token`, `api_key` or `access_key` (so `DB_PASSWORD=`,
`GITHUB_TOKEN=`, `client_secret:`, `aws_secret_access_key =`), followed by
`:` or `=` and a value of at least 6 characters; the password in a URL
(`postgres://user:<password>@host`); `Bearer <token>`; Hugging Face `hf_` tokens;
Singapore NRIC/FIN numbers (any case); Slack webhook URLs; npm `npm_`,
SendGrid `SG.` and Twilio `SK` keys; Azure `AccountKey=` and GCP
`"private_key_id"` values; plain-language credentials ("my password is ...",
"the aws secret is ...", when the value has a digit or symbol or is 16+
characters); Luhn-valid card numbers of 13 to 19 digits; and labelled IBAN and
bank account numbers.

`save` scans the files again before it commits, and also runs
`gitleaks protect --staged` when gitleaks is installed. When either refuses,
the paths it staged are unstaged again, so nothing refused is left in the index.

## Cue pass (the mechanical half of "smarter every exchange")

The cue pass runs on principal lines only, one sentence at a time. The
candidate's statement is the sentence itself, verbatim. The risk is therefore
that a sentence is put in the wrong category, never that words are invented.

| Kind | Patterns (case-insensitive) |
|---|---|
| decision | `let's / we'll / we will / go` + `go with / use / pick / choose / ship / switch to` at the start; `Decision:` / `Final:` / `Decided:`; `I/we (have) decided to/on`; `yes/approved, go/ship/deploy/merge/publish` |
| preference | `from now on`; `always/never answer/reply/use/write/call/send/format`; `I prefer`; `I want/like you/it to` |
| correction | `No,` / `Nope,` at the start; `that's wrong / not right / incorrect`; `Actually,`; `I said`; `stop doing/using` |
| open loop | `remind me`; `follow up`; `waiting for/on`; `by <weekday>` |

- A sentence with a currency amount gets `tier: material`.
- **Register.** A decision goes to an entity's `decisions/` folder only when
  exactly one entity name appears in that same message. Otherwise it goes to
  `brain/decisions/`. Mentions elsewhere in the session are not used.
- **Nudge.** In Claude Code, and in Codex after its hooks are approved, the
  prompt hook prints at most two lines when the current prompt contains a
  cue: `[brain] possible decision: "...". It is recorded automatically after
  this turn; if it is not a decision, say so.` Every 10 undistilled principal
  turns it adds: `[brain] 10 turns since last distill: run brain-distill after
  answering.`

## Verifier (V1-V12)

Every candidate goes through the verifier, whoever proposed it: the cue pass,
`brain-distill`, `decide`, `remember`, onboarding or the operator. A candidate
that fails any rule is rejected and kept, with its reasons, in
`brain/inbox/rejected/`.

| Rule | Check |
|---|---|
| V1 | The quote is an exact substring of the cited line, or of any journal line or current turn. Only whitespace, NFKC and smart quotes are normalised. At least 12 characters. Every `also_quoted` entry must also be a principal's words |
| V2 | For decisions, preferences and corrections, the speaker is a principal with `decides: true`. An assistant, a tool or a non-principal is never the source. A candidate's `speaker` must match its line |
| V3 | An approval (`--approves-quote`) needs the proposal verbatim in an earlier assistant reply of the same session, and the approval within the next 2 principal turns |
| V4 | Every number, amount, date, time, URL and email in the title or statement appears in the quote(s) or the cited line. This rule refuses an invented "S$450" |
| V5 | A duplicate becomes `noop`: the same statement, the same quote, or an overlapping quote from the same line. A `supersedes` target must exist and must not already be superseded |
| V6 | A session that used web, MCP or search never auto-promotes; the candidate goes to review. Neither does a hand-written `journal note`, because the agent writes it, not the runtime |
| V7 | The redaction scan of the quote, statement, title and approval is clean |
| V8 | A decision or preference whose sentence ends with `?`, or has `if / would / could / might / maybe / perhaps / what if / suppose / hypothetically / let's say / in theory / thinking out loud` before its verb, is rejected as `hypothetical`. The same happens when the next sentence says "just thinking out loud" |
| V9 | The target register, relative to `brain/`, matches one of the speaker's `scope` globs |
| V10 | **Statement fidelity.** Every content word of the title and statement appears in the quote or the cited line, and every negation in the quote (`not`, `never`, `stop`, `drop` ...) survives into the statement. A real quote paired with an invented or paraphrased statement goes to **review**; it is never accepted until the operator approves the wording |
| V11 | **Context.** Goes to review instead of auto-accepting when the sentence is reported speech (`Sam said: ...`, `they decided`, a quoted utterance of 3+ words), the message is a pasted block (more than 3 lines, a `>` quote, or `here are the ... notes/email/transcript`), the statement is taken back later in the same message or in the next principal message, or a decision is content-free (`Yes, go ahead.`). A take-back is a later sentence that negates, cancels or forgets a word of the statement (`not Heroku after all`, `forget Heroku`), a take-back marker that names it (`changed my mind`, `on second thought`, `hold off`, `that's not a decision`, `ignore my last message` ...), or a bare take-back (`Actually no.`, `Wait, no.`, `Cancel that.`) directly after it or at the start of the next message; a later sentence with its own substance (`No, that's wrong: the timezone is SGT`) corrects something else and leaves it alone. Also held: a conditional decision (`if`, `unless`, `or not`, `depending on`, `assuming`, `maybe` ...) and a content-free preference or correction (`No, don't do that.`). A take-back that arrives after the earlier message was already promoted moves that unconfirmed record back to `proposed` |
| V12 | **Decisions are candidates.** See [The decision rule](#the-decision-rule) below. A routine decision is never accepted from conversation wording alone: it is accepted only when the operator confirms it, or when its whole session has settled with no later turn that could change it. Anything in doubt waits in review |

V1-V9 reject. V10, V11 and V12 hold: the candidate waits in `brain-review` and
nothing reaches START HERE, `profile.md` or the registers as accepted until
the operator approves it in their own words.

## The decision rule

The rule: **the brain never writes wrong knowledge.** A decision it records as
accepted must be the choice that stands, so a decision found in a conversation
is a *candidate* until one of these is true:

1. **The operator confirms it.** They approve it in `brain-review` (`promote
   <C-id> --quote "..."`, `confirm <id> --quote "..."`), or the assistant asked
   a question that restates exactly that decision ("Want me to set up Postgres
   for the ledger?") and the operator's next turn is a plain yes ("Yes.",
   "Yep, do it."). A confirmation turn sets `confirmed: true` and
   `confirmed_ref` (the journal line of the yes).
2. **Conservative auto-accept** (`learn.auto_accept`, on by default). The
   session has been quiet for `learn.settle_minutes` (default 30), and nothing
   after the decision raises doubt: not the rest of its own message, not a
   later principal turn, not an assistant reply.

Doubt is decided by structure, not by a phrase list. A later principal
sentence is clear only when it is a plain acknowledgement ("Thanks.",
"Great."), a restatement in the decision's own words, or a sentence with no
choice signal at all. Any one of these raises doubt: negation or hesitation
("no", "wait", "hmm", "never"), a switch or take-back marker, a choice verb
("use", "go with", "make it"), a comparison ("overkill", "simpler", "should"),
a question about an alternative, an option the decision did not name
("SQLite", "MongoDB", "v2"), a subject word of the decision, a fragment of
three words or fewer, or another decision or correction. An assistant reply
that offers an alternative (it switches, compares, suggests a choice, names
another option or the decision's subject) makes the operator's next turn doubt
whatever it says: **an alternative the operator agrees to supersedes the
earlier choice.**

This deliberately prefers review to a wrong accept. Unrelated later work ("Now
add tests for the parser.") leaves a decision alone, but many real sessions
will send decisions to review, and the operator confirms them there.
`learn.auto_accept: "off"` sends every unconfirmed decision to review.

`decide` (skill `brain-decide`, the operator asking to record one exact
decision) uses the same reading minus the signals that are not tied to that
decision, so unrelated later work does not hold it; it does not wait for the
session to settle. A later turn on the same subject, a switch or take-back, a
comparison, an alternative question, a bare "no"/"wait" naming an option, or
another choice naming another option still sends it to review.

Configure it in `brain/brain.json`:

```json
"learn": { "auto_accept": "conservative", "settle_minutes": 30 }
```

A decision already accepted goes back to `proposed` when doubt arrives in a
later sync. START HERE, the entity START HERE blocks and `decisions/INDEX.md`
list only accepted decisions, followed by a count: "N decisions awaiting
review (not accepted)". A candidate is never shown as accepted anywhere;
`decisions/ALL.md` and `learned.md` label it "awaiting review, not accepted".
`lint` fails when an accepted decision has a later candidate on the same topic
in its session, when an unconfirmed accepted decision has a later turn that
raises doubt, and when one session holds two accepted decisions on the same
topic.

**Pending verification.** When the quote is found only in `turns.jsonl` (the
current turn, before the runtime's transcript is journaled), the record is
written as `pending-verification`. Every `sync` re-checks it. After 2 failed
syncs it becomes `unverified`: it is listed in review and never shown as a
fact.

**Onboarding answers.** `sync` checks each
`onboarding.answers.<key>.quote` against the operator's journaled words. A
match sets `verified: true` and promotes the onboarding decision
(`D-...-brain-mode`) from `pending-verification` to `accepted`.

## Promotion policy

| Kind | When verified | Destination |
|---|---|---|
| decision, routine | a candidate: `accepted` only when the operator confirms it (`confirmed: true`) or its session settles with no doubt (`confirmed: false`); otherwise it waits in review. See [The decision rule](#the-decision-rule) | the entity's `decisions/` or `brain/decisions/` |
| decision, material (money, people, pricing, contracts) | `proposed` until the operator confirms | same |
| approval of an assistant proposal | as a routine decision, with `authority: approval` | same |
| preference, correction | `active`, `confirmed: false`; with `--supersedes` the old record becomes `superseded` | `brain/profile/`, summarised in `profile.md` |
| fact in a principal's words | `active` | the entity's `facts/` or `brain/facts/` |
| fact from an assistant, tool or external source | review only; `promote` with the operator's words | same |
| open loop | always `proposed` until a principal confirms | the entity's `loops/` or `brain/loops/` |
| skill | never promoted | `brain/skills-drafts/` |

Every promotion adds one line to `brain/learned.md`. The line gives the date,
the kind, the statement, a link to the record, a link to the source line, and
how it came in (`cue`, `distill`, `decide`, `operator`). The next session's
opening snapshot starts with "Since last session I learned N thing(s)".

## Records

Ids are `<T>-YYYYMMDD-HHMM-<slug>`, where T is D (decision), P (preference),
C (correction), F (fact) or L (loop). The time is when the source was said,
in the operator's timezone. A collision gets `-2`. Ids are never reused. The
front matter is flat YAML. The schemas are in `scripts/brain/schemas/`.

**Decisions** carry:
- `source_quote`, `also_quoted`, `source_speaker`, `source_at`;
- `source_ref`: the journal path, then `#L<n>`;
- `source_session` (`runtime:id`);
- `tier`, `authority`, `detected_by`, `confirmed`, `verified`;
- `supersedes` and `superseded_by`;
- `body_sha256` and `meta_sha256`.

The body has `## Context`, `## Decision` and `## Consequences`.

**Immutable.** The body is hashed at acceptance, and `lint` fails on any
later change. The front matter the tool owns (title, statement, status, tier,
decided_by, entity, quotes, source, confirmed, supersede links) is hashed into
`meta_sha256` on every tool write, so a hand edit (a tampered title, a status
flipped to accepted) also fails `lint`. The tool edits front matter only: status, `superseded_by`,
confirmation and verification fields. To change a decision, supersede it.

## Caps (errors, never truncation)

| File | Cap | Over the cap |
|---|---|---|
| `brain/START-HERE.md` | 150 lines / 12 KiB | `index` exits 3 and leaves the file byte-identical |
| `decisions/INDEX.md`, `open-loops.md` | 150 lines / 12 KiB | lists page into `brain/index/*.md` past 40 entries |
| `brain/profile.md` | 12 KiB | the promotion is refused with exit 3, and the file stays byte-identical: "consolidate: brain-review --consolidate" |
| `brain/learned.md` | last 100 entries | older entries move to `brain/archive/learned-YYYY.md` |
| entity `AGENTS.md` | 6 KiB / 100 lines, START HERE within the first 80 lines | `lint` exits 1 |
| AGENTS chain, root to deepest entity | warn at 20 KiB, fail at 24 KiB (Codex cuts silently at 32 KiB) | `lint` exits 1 |
| SessionStart snapshot | 4 KB | cut by section, with a closing line that says so |

## Saved

"Saved" means four things: the file is in its owning folder, it is linked
from its START HERE, it is committed, and it is pushed. `tessbrain.py
status` checks each one and reports:

- uncommitted brain files and unpushed commits;
- files unreachable from `brain/START-HERE.md`;
- files written in the last 7 days under `kb/`, `clients/*/`, `missions/` or
  `.tess/state/` that git ignores or the gate refuses ("move to brain/...");
- sessions not yet journaled;
- the inbox, what was learned since the last session, budgets and errors.

`tessbrain.py save -m "<message>"` (1) regenerates the indexes, (2) refuses
any unreachable file and names the link to add, (3) stages only `brain/` and
the state-card folder, (4) scans for secrets and runs gitleaks when installed,
(5) commits, with the repository's own hooks always running (the tools never
bypass them), and (6) pushes only when `save.autopush` is on and the remote is
neither the public framework repository nor reported public by `gh`. It
checks every URL `git push` would write to (`git remote get-url --push --all`,
so a `pushurl` or `pushInsteadOf` cannot route around the check).

If the ship-gate refuses a new instance's first push, the tool points to the
one-time operator seed push in the onboarding guide.

## Review, correct, retract, reject

- `tessbrain.py review` gives a numbered list with the verifier's reasons.
  Skill `brain-review` shows it and applies the operator's answer.
- `confirm <id> --quote "<their words>"` sets `confirmed: true`. For a
  proposed decision it also sets `accepted`.
- `reject <id> --quote "..."` marks a record `rejected` ("that was not a
  decision"). The record is kept for history.
- `retract <id> --quote "..."` writes a superseding C- record and marks the
  old one `retracted`. `learned.md` shows "(now retracted)".
- `promote <C-id> --quote "..."` approves an inbox candidate that was held for
  review.

Every one of these commands checks that the quote is really a principal's
words, in the journal or the current turn.

## Decisions

A decision is detected in five ways:

1. the cue pass, at every sync;
2. the prompt nudge, while the decision is being typed;
3. the BOOT "Record" rule, through skill `brain-decide`: `tessbrain.py decide
   --register ... --title ... --statement ... --quote "..." [--supersedes
   D-...] [--tier material] [--kind decision|requirement|constraint|question]`;
4. `brain-distill`, for implicit decisions;
5. the onboarding answers.

Generated registers:
- `decisions/INDEX.md`: accepted decisions only, per entity and globally, a
  count of decisions awaiting review, and an open-questions section;
- `decisions/ALL.md`: the full history;
- the latest 5 accepted decisions in each START HERE, plus the count of
  decisions awaiting review.

Delegated decisions carry `authority: delegated` and a `delegation_ref`.

## Privacy

- Never in git: `.tess/state/brain/` and `brain/.private/`. Whichever tool
  creates one of these directories first writes a `.gitignore` containing `*`
  inside it.
- Never in `brain/`: secrets, government IDs, pay, health or HR records, or
  contract files. Write a pointer to where they live instead.
- `lint` fails a person file that has any of these keys: salary, pay,
  compensation, equity, bank, dob, birthday, nric, fin, passport,
  government_id, address, home_address, personal_phone, personal_email,
  health, medical, diagnosis, disability, performance, rating, review, pip,
  disciplinary, grievance, gwc, religion, ethnicity, marital or family. It
  also fails one that contains an NRIC/FIN-shaped value.
- Anything the agent reads is sent to that runtime's model provider,
  `.private/` included.

## Commands

| Command | Does |
|---|---|
| `sync [--runtime all\|claude\|codex\|gemini]` | journal, cue pass, verify, promote, index |
| `journal note --text "..."` | note a turn by hand, for runtimes without capture; held for review |
| `decide`, `remember`, `inbox add` | record through the verifier |
| `confirm`, `reject`, `retract`, `promote`, `review` | operator review, in the operator's own words |
| `index`, `lint`, `status`, `save`, `recall` | indexes, integrity, "saved", search |
| `hook session-start\|prompt\|stop --runtime claude\|codex` | runtime hooks; they always exit 0 |
| `githooks install` | warn-only pre-commit lint and post-merge index regeneration |

Every hook is silent under `TESS_BRAIN_QUIET=1` or `TESS_HEADLESS=1`, in the
Tess OS source repo, and wherever `brain/brain.json` is missing.
