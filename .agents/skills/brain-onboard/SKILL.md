---
name: brain-onboard
description: "START HERE when brain/brain.json is missing or onboarding is not complete: run the 7-step second-brain interview (personal / agency / organisation), one question per turn, recording each answer with the operator's exact words, then build and commit the brain. Also handles 'later' (defer), 'skip onboarding', 'convert this clone' and 'add a client/person/project/area/unit/seat'."
---

# brain-onboard

Sets up this Tess OS instance as the operator's second brain. The tool does
the writing: `python3 scripts/brain/onboard.py` (stdlib only). You ask, the
operator answers, the tool records. Answer the operator in plain words; never
show them JSON unless they ask.

## 1. Always check state first

Run `python3 scripts/brain/onboard.py status --json` before anything else.

| `status` | What you do |
|---|---|
| `source-repo` | This is the Tess OS framework repo. Do not onboard. Offer `npm create tess@latest <folder>`, or section 5 if the operator says "convert this clone". |
| `pending` or `in_progress` | Greet the operator by the assistant name (default Tess), then ask the question for `step` (use `next_question`; `missing` lists the fields still needed). Resume at the saved step; never restart from step 1. |
| `deferred` | Say nothing about onboarding unless the operator brings it up. |
| `complete` or `skipped` | Onboarding is done. Never ask the interview again. Use `add` / `add-mode` (section 6) for changes. |

A session started only to carry out a task handed over by another agent
skips onboarding entirely.

## 2. The interview: one question per turn

Ask exactly one step per turn, in order. After each reply, record every field
that step needs, then ask the next step.

1. **Mode** (field `mode`): "Who is this brain for? (a) just me: personal, (b) my firm, serving outside clients: agency, (c) an organisation with a team and roles: organisation. More than one is fine." Value: `personal`, `agency`, `organisation`, or several comma-separated, primary first.
2. **Preset** (field `preset`): agency: `solo-consultant` or `none`; organisation: `startup` or `none`; personal: skip the question and record `none` with the operator's step-1 words.
3. **Identity** (fields `operator_name`, `address_as`, `assistant_name`, `timezone`): their name and how to address them; your name (default Tess); their timezone (show `detected_timezone` from status and ask them to confirm; IANA name such as `Europe/Lisbon`).
4. **Principals** (field `principals`): "Besides you, whose words count as decisions here, and for what?" Value: `none`, or JSON like `[{"name": "Jon Park", "scope": "clients/northwind-studio/**"}]` (scope is relative to `brain/`; `**` = everything). Everyone else's words are recorded as facts, never as decisions.
5. **Seed entities**: agency: `agency_name`, `agency_offer` (one line), `clients` (up to 3). Organisation: `org_name`, `operator_seat`, `seats` and/or `units` (up to 5), `serves_clients` (yes/no). Personal: `areas` (work, home, relationships, learning, health\*, money\*; \* = always private) and `projects` (up to 3). Lists are comma-separated or JSON.
6. **Memory and privacy** (field `journal`): `commit-redacted` (default for personal and agency), `stub-only` (default for organisation; bodies stay local) or `local`. Tell them, in one line: anything you read is sent to this runtime's model provider, including `brain/.private/`.
7. **Remote and runtimes** (fields `remote_url`, `autopush`, `runtimes`): a PRIVATE git remote URL or `later`; push automatically after save (yes/no); which CLIs they use (claude, codex, gemini, kimi). Then give the trust line for each runtime they named (section 4) and the seed-push line (section 3).

Record each field:

```
python3 scripts/brain/onboard.py answer --step N --field FIELD --value "VALUE" --quote "THE OPERATOR'S EXACT WORDS" --runtime claude-code|codex|gemini|other
```

Rules for answers:

- `--quote` is copied verbatim from the operator's message: their words, not yours. Several fields from one message share that message as the quote.
- Never invent or paraphrase an answer. Never fill a field the operator did not answer: ask again, or offer the default and record it only after they accept (their acceptance is the quote).
- Never record your own suggestion, a question, or a hypothetical ("maybe", "what if") as their answer.
- Re-answering a field overwrites it; that is how the operator corrects an answer.

## 3. Apply

When `status --json` shows `"ready_to_apply": true`, run:

```
python3 scripts/brain/onboard.py apply
```

It creates the mode tree under `brain/` (create-only: existing files are
never overwritten), writes the first decision (`brain/decisions/D-...-brain-mode.md`,
status `pending-verification`, the operator's step-1 words as its quote),
and commits `brain/` and `memory/projects/` through the installed gate
hooks. Then tell the operator, briefly: what was created, three things to
try ("Tell me about <client>", "What did we decide about X?", "From now on,
..."), and the one-time seed push they run themselves after reading
`git log`: `git push --no-verify -u origin main`. You never run
`--no-verify` yourself and never push to a public remote.

Exit code 3 means "not ready" (answer the remaining steps) or "source repo".
Exit code 4 means git or tessctl failed: show the operator the message.

## 4. Trust steps, one line per runtime they use

- **Claude Code**: one workspace-trust click. It enables the brain hooks (onboarding reminder, capture) and the tool permissions; CLAUDE.md, commands and skills work without it.
- **Codex CLI**: nothing is needed to start. Optional: trust the project and approve the Tess hooks in `/hooks` for per-turn capture; approval is pinned to the hook text, so re-approve after an update.
- **Gemini CLI**: one folder-trust click. It loads GEMINI.md and the `/tess:*` commands; `.agents/skills` works without it.
- **Kimi and other AGENTS.md tools**: nothing to configure; Tess works from AGENTS.md instructions only.

## 5. Defer, skip, convert

- "later" / "not now": `python3 scripts/brain/onboard.py defer --days 7`. The reminder comes back after 7 days.
- "skip onboarding": `python3 scripts/brain/onboard.py skip --quote "THEIR EXACT WORDS"`. It sets up the personal layer only with defaults and records the skip.
- "convert this clone" (only when status is `source-repo`): explain that it renames the framework remote `origin` to `upstream` and marks this clone as an instance, then after they agree run `python3 scripts/brain/onboard.py convert-clone --yes`, ask for a PRIVATE remote (`git remote add origin <url>`), and start the interview at step 1.

## 6. After onboarding

- New client, person, project, area, unit or seat: `python3 scripts/brain/onboard.py add client "Name"` (project needs `--in <client-slug>` in agency mode). It writes the index line first, creates only, and prints `skipped (exists)` for anything already there.
- Another mode: `python3 scripts/brain/onboard.py add-mode organisation --quote "THEIR EXACT WORDS"`. Nothing is moved or renamed; a decision is recorded.
- Fresh clone missing `operator/profile.json`: `python3 scripts/brain/onboard.py restore`.
- Saving later work: skill `brain-save` (`python3 scripts/brain/tessbrain.py status`) when that tool exists; otherwise commit the `brain/` paths with git.
