# When Tess stops a push

Tess OS checks every `git push` from your folder. If the push changes one of
Tess's own safety files (its rules, its hooks, its engine), Tess stops it and
prints a short message like this:

```
Tess stopped this push because it changes 1 protected file(s):
    conductor/guardrails.md
What this means: these files hold Tess's own safety rules, so a change to them
needs a signed approval before it can leave this computer. Nothing was sent.
To undo your change (puts the file(s) back and saves that):
    git restore --source=1a2b3c4d5e6f -- conductor/guardrails.md
    git commit -m "Undo change to protected Tess files" -- conductor/guardrails.md
  then push again. Or ask your assistant: "undo my change to conductor/guardrails.md".
More help: docs/WHEN_TESS_STOPS_A_PUSH.md
```

Nothing was sent anywhere. Your work is still on this computer, saved in git.

## If you did not mean to change that file

Most of the time the change was an accident: an assistant edited a rules file
while doing something else, or a file was saved by mistake.

1. Copy the two lines Tess printed under "To undo your change" into your
   terminal, one at a time. The first puts the file back the way it was; the
   second saves that. Tess prints the exact commit to use, so you do not have
   to work it out.
2. Push again.

Or ask your assistant in Claude Code or Codex: "undo my change to
`<the file name>`, then push again". It can run the same two commands.

If Tess named more than five files, it does not print the undo commands,
because putting many files back at once is rarely what you want. Ask your
assistant, or a helper, to look at them with you first. To see the full list:

```
TESS_VERBOSE=1 git push
```

## If you meant to change it

A change to Tess's own safety files needs a signed approval (a "verdict") from
a reviewer whose key this project trusts. A new folder has no reviewer keys
yet, on purpose: nobody, including an AI assistant, can approve its own change
to the rules. Setting up reviewer keys is a one-time job for someone
comfortable with git and signing keys; see
[Gate operation and custody](GATE_QUICKSTART.md), "What to do when blocked".

## First push of a new folder

A folder made with `npm create tess` carries the proof of the signed Tess OS
release it came from (`.tess/release-proof.json`). Its first push passes as
long as Tess's files are exactly that release.

If Tess says "this is the first push of this folder, and Tess cannot confirm
that its own files are an unchanged Tess OS release", the folder was made another way (a git clone, a copy,
or `--template-source`), or a Tess file was edited before the first push.
Either:

- make a new folder with `npm create tess@latest` and move your own work into
  it, or
- keep this folder on this computer only (it is saved in git; back it up like
  any other folder) until reviewer keys are set up
  ([Gate operation and custody](GATE_QUICKSTART.md)).

## When Tess stops something inside Claude Code or Codex

Tess also checks your assistant's actions while you work. If it blocks one,
the assistant sees a message starting with `TESS GATE:` that says why and what
to do instead, and should tell you. Two kinds:

- **Blocked**: editing Tess's own safety files, skipping git's safety checks
  (`--no-verify`), printing a login token, or sending brain or client data to
  a public place. These are never allowed from inside a session.
- **Needs your OK** (Claude Code asks you; Codex cannot ask, so it blocks and
  tells you to run it yourself): force pushes, changing where the folder is
  pushed to, and making a repository public or private.

## Never skip the check

Do not use `git push --no-verify` or change git's hooks setting to get past
Tess. Inside Claude Code and Codex, Tess blocks both. The check is what keeps
an assistant from quietly changing its own rules.
