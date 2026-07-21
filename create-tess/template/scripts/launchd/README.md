# Memory-continuity heartbeat — launchd example (macOS)

**Status: template, not activated. Nothing here has been placed in
`~/Library/LaunchAgents/`, and no `launchctl load`/`bootstrap` has been run
by this repository.** A persistent scheduler spawning `claude -p` and
sending notifications on an operator's behalf is a materially different
trust boundary than an interactive session, so this ships inert until the
operator deliberately turns it on — matching this framework's own
gate-off-by-default posture (empty verifier/sign-off registries, fail-closed
by design) applied to a second, unrelated subsystem.

`~/Library/LaunchAgents/` is **not actually inert once a file is placed
there** — `launchd` rescans it at every GUI login/logout (not only via an
explicit `launchctl load`), so a real plist sitting there could self-activate
on the next reboot or log-out/log-in without anyone running a command.
Staging the plist as a `.template` here (rather than a ready-to-copy
`.plist`) keeps "do not activate" true regardless of what happens to the
machine in the meantime — an operator has to substitute real paths and
choose a new filename before it becomes something `launchd` would even
recognize.

Other schedulers (cron, systemd user timers, Windows Task Scheduler) work
too — `scripts/heartbeat.sh` has no macOS-specific dependency beyond being a
bash script; only this particular staged example is launchd-specific.

## Two independent switches — both must be flipped

1. **`scripts/heartbeat/heartbeat.config.json`**: set `"activated": true`
   (or export `TESS_MEMORY_HEARTBEAT_ACTIVATED=1` in the scheduler's
   environment). Until this is true, `run.py` forces `--dry-run` regardless
   of what invokes it — see `scripts/heartbeat/run.py`'s module docstring.
2. **The scheduler itself** (this plist, or your own cron/systemd
   equivalent) — the steps below.

## One-command activation (macOS launchd)

```bash
# 0. Set the real state you want, first:
#    - flip "activated": true in scripts/heartbeat/heartbeat.config.json (or set
#      TESS_MEMORY_HEARTBEAT_ACTIVATED=1 for the launchd EnvironmentVariables key)
#    - pick a notify.channel in the same file and export its secret env var
#      (see docs/memory-continuity.md)

# 1. Render the template with your real absolute repo/home paths, e.g.:
sed -e "s#/ABSOLUTE/PATH/TO/REPO#$(pwd)#g" \
    -e "s#/ABSOLUTE/PATH/TO/HOME#$HOME#g" \
    scripts/launchd/com.tess-os.memory-heartbeat.plist.template \
    > /tmp/com.tess-os.memory-heartbeat.plist

# 2. Copy the rendered plist into the real LaunchAgents directory
cp /tmp/com.tess-os.memory-heartbeat.plist \
   ~/Library/LaunchAgents/com.tess-os.memory-heartbeat.plist

# 3. Load it (modern, non-deprecated form)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.tess-os.memory-heartbeat.plist

# --- To deactivate later ---
launchctl bootout gui/$(id -u)/com.tess-os.memory-heartbeat
rm ~/Library/LaunchAgents/com.tess-os.memory-heartbeat.plist
```

(`launchctl load`/`unload` still work as a legacy fallback if
`bootstrap`/`bootout` ever misbehave on your macOS version, but
`bootstrap`/`bootout` are the current, non-deprecated subcommands.)

`RunAtLoad` is `true` in the template, so the first pass fires immediately
on load — check `<state_dir>/launchd.out.log` right after to confirm it ran
(default state dir: `~/.tess-os/memory-heartbeat/`, see
`scripts/heartbeat/config.py`).

## Known limitations (honest, not hidden)

- **launchd pauses when the machine sleeps.** This is a laptop-scoped
  heartbeat, not a durable server-side one. A stall that occurs while the
  machine is asleep is only caught on the next wake — late, not lost, since
  `since` is recomputed from evidence each run, not from "how many ticks
  have I done."
- **`git push` from a scheduler-spawned process is unverified in every
  environment.** `gh` auth is typically file-based and should work headless,
  but whether your `git push` remote (SSH agent socket, credential helper)
  is reachable from a launchd/cron-spawned background process depends on
  your own machine's auth setup — verify this once, live, before trusting
  the daily recompile's commit+push unattended.
- **The `claude -p --output-format json` response shape has been observed to
  vary** (a JSON array of turn objects in some versions vs. a single result
  dict) — `tier2_classify.py`'s parsing handles both defensively, but this
  deserves one real smoke-test call at first activation before being
  trusted unattended (see docs/memory-continuity.md's activation checklist).
