# Demo recording

`tess-demo.svg` (embedded in the root [README](../../README.md#see-it)) is a
real, unedited terminal recording, not a mockup. It shows two things back to
back:

1. **The `create-tess` wizard**, driven through its five axes (vibe, operator
   name, starter path, conductor name, pathway) — picking the Guild vibe, the
   founders starter squad, and the default Chief of Staff pathway — ending on
   the real post-bake `tessctl doctor`/`tessctl verify` checks and the
   conductor's in-voice arrival greeting.
2. **The Agent Receipt "show me the receipt" demo** (`make receipt-demo`) —
   propose → approve → sign → journal → verify, with two real, ephemeral,
   test-only GPG identities, ending in a chain-intact verification and a
   negative control (a tampered copy is correctly rejected).

Nothing in the cast is hand-typed after the fact or trimmed to hide an error;
`tess-demo.cast` is the raw [asciinema](https://asciinema.org) recording the
SVG was rendered from, kept alongside it for anyone who wants to check.

## How it was made

- The wizard's interactive prompts are driven over a **real pty**
  (`driver.py`), not the `--yes`/flags non-interactive mode — the recording
  shows the actual `@clack/prompts` UI a user sees, not a flag-driven
  shortcut. `driver.py` strips ANSI codes from its own internal copy of the
  output to decide when each prompt has rendered and it's safe to send the
  next keystroke; the raw, unmodified bytes are passed straight through to
  the recorder.
- Recorded with `asciinema rec`, converted to SVG with
  [`svg-term-cli`](https://github.com/marionebl/svg-term-cli) (`agg` was not
  available in the environment this was built in — no Rust/cargo toolchain —
  so the asciinema → GIF path via `agg` wasn't an option; `svg-term-cli`'s
  animated-SVG output was used instead, which needed only `npx`).

## Gotcha worth keeping if you touch this

`pty.fork()` leaves the child's pty with **no window size set** (0 rows/cols).
Width-sensitive rendering (box borders, the `@clack` reveal animations) then
breaks in a confusing way — every character lands on its own line, as if each
one were individually styled. Fix: set a real winsize with `TIOCSWINSZ`
immediately after `fork()` (see `driver.py`). This is a pty issue, not a bug
in the wizard.

## Reproduce it

```bash
pip install asciinema           # or: pipx install asciinema
(cd create-tess && npm install) # once, if not already done
docs/demo/record-demo.sh
```

Requires Python 3, Node.js, `gpg`, and network access (for the one-shot
`npx svg-term-cli` conversion). Regenerates both `tess-demo.cast` and
`tess-demo.svg` in place.
