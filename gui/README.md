# tess-gui — Tess OS Mission Control (v0)

An optional, local dashboard for Tess OS: a Mission Launcher, Live Mission
View, Metrics Panel, and Roster Browser, all running on top of your own
already-installed and authenticated `claude` CLI.

This is a thin Node HTTP server bound to `127.0.0.1` that spawns `claude`
locally and streams its output to a vanilla-JS dashboard in your browser.
It is entirely optional — Tess OS works fully without it.

## Status

v0. Not published to the npm registry — it ships inside this repo and runs
repo-local. A `tessctl gui` subcommand shim and/or a registry publish are
possible fast-follows once there's real usage demand.

## Quickstart

From your Tess OS instance root:

```bash
node gui/bin/tess-gui.mjs
```

This starts the server, prints the dashboard origin, and opens your browser.
If the browser doesn't open automatically, or you're on a headless machine,
run:

```bash
node gui/bin/tess-gui.mjs --print-token
```

to print the full URL (including your one-time session token) so you can
open it manually or copy it to another device on the same machine.

Other flags: `--port <n>` (default: auto-assigned free port), `--dir <path>`
(project root to operate on; default: current directory), `--no-open` (skip
the automatic browser launch).

`--dir` defaults to the current working directory, so run the command from
your Tess OS instance root (where `.claude/commands/` and `agents/` live) —
not from inside the `gui/` folder itself. Running it from `gui/` will show an
empty command list and roster, since it'll look for `.claude/commands/` and
`agents/` inside `gui/` instead of the real instance root. If you're not in
the instance root, pass `--dir` explicitly instead:

```bash
# from the instance root
node gui/bin/tess-gui.mjs

# from elsewhere
node /path/to/instance/gui/bin/tess-gui.mjs --dir /path/to/instance
```

## Requirements

- A supported Node.js LTS release: Node.js 22.13.0 or newer on the 22.x line,
  or Node.js 24.x. The GUI test dependency (`jsdom@29`) does not support the
  older Node.js versions previously claimed here, and Node.js 18 and 20 are
  end-of-life.
- The Claude Code CLI installed and already logged in
  (`claude auth status` should show you as authenticated)
- Minimum supported CLI version: **2.0.0**. `tess-gui` runs a startup
  preflight check. The dashboard keeps its launch controls disabled until
  `/api/health` reports a compatible CLI, including while that check is
  unresolved or the local server cannot be reached.

### Launch admission

The dashboard preflight is a conservative usability check, not an authority
boundary or a diagnostic interface. `POST /api/missions` on the local server
is authoritative: it repeats its own compatibility check immediately before
spawning a mission and rejects unavailable, missing, unresolved, failed, or
incompatible CLI health. The browser may therefore disable a launch that the
server could later accept, and the server may still reject a request after a
compatible browser health response. The UI does not promise to diagnose why a
launch was rejected.

## Known first-run behavior

On a freshly cloned or not-yet-trusted workspace, the spawned `claude` CLI
may print a one-time warning in the live mission log, such as:

```
Ignoring N permissions.allow entries... this workspace has not been trusted
```

This is expected Claude Code behavior for new workspaces, not a `tess-gui`
bug — the mission still completes normally.

## Security model

- The server binds to `127.0.0.1` only — it is never reachable from the
  network.
- Every launch generates a fresh, random, per-session token. All dashboard
  routes require it.
- The full tokened URL is never printed to stdout/terminal by default —
  terminal scrollback, tmux history, and CI logs all persist plaintext, and
  this token is effectively an RCE-equivalent credential (it authorizes
  spawning `claude` on your machine). Use `--print-token` if you need it.
- `tess-gui` never reads `.claude/vault/` or `.claude/tess-secrets/`, and
  never handles or stores your Claude Code credentials itself.

**Disclosure:** tess-gui drives your own locally installed and authenticated
Claude Code CLI. It does not provide, proxy, or embed claude.ai login, does
not handle Anthropic credentials, and is not affiliated with or endorsed by
Anthropic.

## License

Apache-2.0 — see [LICENSE](./LICENSE) and [NOTICE](./NOTICE) (both exact
copies of the repo root files, per Apache-2.0 §4(d), since this package can
be redistributed independently of the rest of the repo).
