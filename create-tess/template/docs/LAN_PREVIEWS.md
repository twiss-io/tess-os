# Portable local-network previews

Every new `create-tess` installation includes `scripts/preview/tesspreview.py`.
Installing Tess does **not** start a server or expose any files. Starting a
preview explicitly exposes the selected public files over unauthenticated HTTP
to peers that can reach this host. Choose only approved public material.

Requirements: Python 3.9+, macOS or Linux. Windows uses WSL, as in the
[local development quickstart](LOCAL_DEV_QUICKSTART.md); native PowerShell/CMD
is not supported. No npm/Python runtime dependency, privileged installation,
public hosting, tunnel, router forwarding or firewall change is required.

## Start and hand off

Build or copy the approved preview into an isolated public directory, separate
from your workspace, brain, KB, credentials and control state. Pass the physical
directory path: symlink directories/ancestors are rejected (on macOS use the
physical `/private/...` path instead of `/tmp` or `/var` aliases). Explicitly
select **every** required file and nested asset; the launcher never walks and
publishes a whole directory. No glob expansion or automatic asset discovery is
performed. A filename must use ASCII letters/digits, dots, hyphens or underscores
and each path component must start with a letter/digit.

```sh
python3 scripts/preview/tesspreview.py start demo --public-dir /physical/path/to/public \
  --file index.html --file assets/app.js --file assets/site.css --file assets/logo.svg --spa
python3 scripts/preview/tesspreview.py verify demo
```

The default public listener binds `0.0.0.0`. The OS chooses an available port
atomically; an optional `--port 8000` is a preference, not permission to stop an
occupied listener. An occupied preferred port falls back to an OS-assigned port.
Distinct project slugs get independent processes/ports. Duplicate running slugs
are refused. A slug is lowercase kebab-case, at most 64 characters.

For a local-only preview add `--localhost-only`: it binds `127.0.0.1` and prints
no LAN link. If LAN-address detection fails, a LAN-bound server still runs but
the handoff explicitly reports that only the localhost link is available. Use
local-only mode if you do not want any LAN exposure. Linux/WSL detection uses
`ip -j -4 addr show up` (iproute2); macOS uses `/sbin/ifconfig`. No Internet/DNS
probe or fixed address is used. With multiple interfaces, the first usable
non-loopback IPv4 address is selected; verify it is the intended LAN.

Start, status and verify print clickable Markdown links:

- **This computer:** `http://127.0.0.1:<chosen-port>/dev/<slug>`
- **Other computers on the same LAN:** `http://<current-lan-ip>:<chosen-port>/dev/<slug>`

Always run `verify` before saying a preview is ready. It checks both available
addresses, bytes of **all selected assets**, trailing-slash redirect, deep-link
behavior, isolation, and private/traversal-path denials. These are host-side
checks, **not** evidence that another physical device loaded the preview.
WSL virtual networking, Wi-Fi client isolation and host firewall rules may
prevent another device from reaching it even when host-side checks pass. This
launcher does not modify those controls; report the limitation instead.

Keep the host awake and connected to the LAN. Links are HTTP, local-network
only, not TLS or public availability. Status/verify re-detect the current LAN
address; do not copy an old address from a previous session.

## URL and asset-base contract

`/dev/demo` redirects with HTTP 308 to `/dev/demo/`, discarding query parameters.
`index.html` is served at the trailing-slash route. Relative nested assets such
as `assets/site.css` work there. For SPA deep links, use `--spa` and build with
base `/dev/demo/`, or put this in the HTML head **before** relative asset tags:

```html
<base href="/dev/demo/">
<link rel="stylesheet" href="assets/site.css">
```

The server does not rewrite HTML/JS/CSS. Root-absolute `/assets/...` URLs must
be changed by the build to `/dev/demo/assets/...`. With `--spa`, safe unlisted
extensionless routes (including routes ending in `/`) return the selected
index; missing asset paths with extensions still return 404. Without `--spa`,
unlisted paths return 404. Directory listings are never generated. Private and
hidden names are rejected before SPA fallback. Each process serves only its
own slug, not another project's route or internal workspace paths.

## Lifecycle, freshness and private state

```sh
python3 scripts/preview/tesspreview.py status demo
python3 scripts/preview/tesspreview.py logs demo
python3 scripts/preview/tesspreview.py restart demo
python3 scripts/preview/tesspreview.py stop demo
```

The detached process survives the launching shell. Handoffs include its PID,
log path and exact verification/status/restart/stop commands. Stop authenticates
a random per-instance token on a **separate loopback-only** control listener
and waits for the process's exclusive lock to release. It never sends a PID
signal, so a stale/reused PID cannot kill an unrelated process. A stale record
reports stopped/stale; `restart` retries the saved approved selection and the
exclusive lock prevents duplicate servers. Startup timeouts are unconfirmed,
not success: check status/logs before retrying. Logs contain lifecycle messages,
not request URLs, headers or the control token.

Default private state is `.tess/state/previews/` in this installation, mode
0700, with mode-0600 records/logs/locks. An existing less-restrictive state
directory is refused. Global `--state-dir /physical/private/state` can select
a different owner-only directory. Do not delete or replace active lock files
or state directories. They and the public directory must be controlled by the
operator; malicious processes running as the same OS user are outside this
local preview boundary. `--json` emits a machine-readable handoff, omitting
the control token and including `second_device_tested: false`.

Files are snapshotted into memory on explicit start/restart and are **not live**.
Edits, new files, root replacement and symlink changes do not expand a running
server's file set. Restart after a new build, then verify again. Limits are
512 selected files, 16 MiB per file, 64 MiB total snapshot; launch fails closed
above these limits. HTTP concurrency is bounded to 16 requests per listener
with a five-second socket timeout. Preview is not a production web server.

## Security boundary and validation

Files are opened relative to pinned directory descriptors using `O_NOFOLLOW`,
including each nested component. Only regular, non-hardlinked files with
approved web/media/font extensions are accepted. Hidden/control names, common
private directories, credential names/types, source maps and arbitrary file
types are refused even if selected. Common broad roots (home, filesystem,
workspace/brain/KB) are refused. Content changes during reading are detected.
Serving requests reads only the immutable allowlisted byte snapshot, never the
filesystem. URL traversal, encoded separators, double encoding and controls
are rejected; HTTP errors never contain source paths.

This is an exposure boundary, not a content classifier: an innocently named
`public-data.json` or image can contain confidential data. Explicit human/agent
approval of the **actual selected bytes** is still required. Do not use this
tool for credentialed apps, unapproved client documents or private data.

Safe targeted validation (no signing fixtures):

```sh
python3 -m pytest tests/test_lan_preview.py -q
node --test create-tess/test/lan-preview-install.test.js
```

Run the same tests natively on macOS and Linux, and inside WSL on Windows;
mocked interface-selection branches are not native OS validation. Test artifacts
and listeners are synthetic and isolated. The feature's review record must
name which platforms actually ran; unsupported/unavailable hosts are unverified.

Primary API references: [descriptor-relative file operations](https://docs.python.org/3/library/os.html),
[detached subprocess sessions](https://docs.python.org/3/library/subprocess.html),
[socket binding](https://docs.python.org/3/library/socket.html), and
[WSL network behavior](https://learn.microsoft.com/en-us/windows/wsl/networking).
