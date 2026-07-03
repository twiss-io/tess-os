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

## Requirements

- Node.js >= 18
- The Claude Code CLI installed and already logged in
  (`claude auth status` should show you as authenticated)
- Minimum supported CLI version: **2.0.0**. `tess-gui` runs a startup
  preflight check and will fail loudly with an upgrade message rather than
  surface a raw CLI error mid-mission if your version is older.

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
