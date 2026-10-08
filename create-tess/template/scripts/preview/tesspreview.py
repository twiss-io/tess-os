#!/usr/bin/env python3
"""Portable explicit-start LAN previews. Python 3.9+, standard library only."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import sys

from content import PreviewError, directory, require_platform
from lifecycle import control, private_file, read_record, serve, start, stop, verify
from server import lan_ip, network_status

SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SCRIPT = str(Path(__file__).resolve())
DEFAULT_STATE = str(Path(SCRIPT).parents[2] / ".tess" / "state" / "previews")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-dir", default=DEFAULT_STATE, help="Private mode-0700 lifecycle directory")
    p.add_argument("--json", action="store_true", help="Machine-readable handoff (never includes control token)")
    sub = p.add_subparsers(dest="command", required=True)
    launch = sub.add_parser("start", help="Explicitly expose ONLY selected public preview files")
    launch.add_argument("slug")
    launch.add_argument("--public-dir", required=True, help="Physical isolated public build directory (no symlinks)")
    launch.add_argument("--file", action="append", required=True, help="Approved relative file; repeat for every asset")
    launch.add_argument("--port", type=int, default=0, help="Preferred port; occupied port falls back to OS-selected free port")
    launch.add_argument("--localhost-only", action="store_true", help="Disable LAN exposure; bind only 127.0.0.1")
    launch.add_argument("--spa", action="store_true", help="Return selected index.html for safe extensionless deep links")
    for command in ("status", "verify", "stop", "restart", "logs"):
        sub.add_parser(command).add_argument("slug")
    return p


def handoff(record, checked=None):
    address = None if record["host"] == "127.0.0.1" else lan_ip()
    route = "/dev/" + record["slug"]
    base = [sys.executable, SCRIPT, "--state-dir", record["config"]["state_dir"]]
    result = {
        "slug": record["slug"], "pid": record["pid"], "instance": record["instance"],
        "bind": record["host"], "port": record["port"],
        "localhost_url": f"http://127.0.0.1:{record['port']}{route}",
        "lan_url": f"http://{address}:{record['port']}{route}" if address else None,
        "lan_limitation": "Localhost-only mode; LAN sharing disabled." if record["host"] == "127.0.0.1"
                          else network_status()["limitation"],
        "log_path": str(Path(record["config"]["state_dir"]) / (record["slug"] + ".log")),
        "snapshot_files": len(record["assets"]), "snapshot_bytes": record["snapshot_bytes"],
        "host_verified_addresses": checked or [], "second_device_tested": False,
        "commands": {name: shlex.join(base + [name, record["slug"]])
                     for name in ("verify", "status", "logs", "restart", "stop")},
    }
    return result


def display(result, json_output):
    if json_output:
        print(json.dumps(result))
        return
    print(f"[This computer]({result['localhost_url']})")
    if result["lan_url"]:
        print(f"[Other computers on the same LAN]({result['lan_url']})")
    else:
        print("LAN link unavailable: localhost-only mode or no usable LAN IPv4 address detected.")
    if result["lan_limitation"]:
        print(result["lan_limitation"])
    print(f"Bind: {result['bind']}; PID: {result['pid']}; log: {result['log_path']}")
    if result["host_verified_addresses"]:
        print("Host-side assets, deep links and denied paths verified on: " + ", ".join(result["host_verified_addresses"]))
    else:
        print("Running; not yet verified. Run the verification command below before handoff.")
    print("No second physical device was tested. Keep the host awake and connected to the LAN.")
    print("HTTP only; LAN peers can read selected assets. No tunnel or firewall change is configured.")
    for name, command in result["commands"].items():
        print(name + ": " + command)


def main(argv=None):
    args = parser().parse_args(argv)
    require_platform()
    if not SLUG.fullmatch(args.slug) or len(args.slug) > 64:
        raise PreviewError("Use a lowercase kebab-case project slug of at most 64 characters.")
    args.state_dir = os.path.abspath(args.state_dir)
    if args.command == "start":
        if not 0 <= args.port <= 65535:
            raise PreviewError("Port must be 0 to 65535.")
        config = {"slug": args.slug, "state_dir": args.state_dir,
                  "public_dir": os.path.abspath(args.public_dir), "files": args.file,
                  "port": args.port, "localhost_only": args.localhost_only, "spa": args.spa}
        print("Starting explicit public snapshot; " + ("localhost only." if args.localhost_only else
              "LAN peers can read every selected file (0.0.0.0 bind)."), file=sys.stderr)
        record = start(config, SCRIPT)
    elif args.command == "logs":
        with directory(args.state_dir, private=True) as root:
            fd = private_file(root, args.slug + ".log", os.O_RDONLY)
            with os.fdopen(fd, "r") as stream:
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size - 16384))
                print(stream.read())
        return 0
    else:
        record = read_record(args.state_dir, args.slug)
        if args.command == "stop":
            stop(record)
            print(json.dumps({"slug": args.slug, "stopped": True}) if args.json else "Preview stopped; lock released.")
            return 0
        if args.command == "restart":
            try:
                control(record)
            except PreviewError:
                pass  # stale: start's exclusive lock still prevents duplicates
            else:
                stop(record)
            record = start(record["config"], SCRIPT)
        else:
            control(record)
    checked = verify(record) if args.command == "verify" else None
    display(handoff(record, checked), args.json)
    return 0


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["_serve"]:
            serve(json.loads(sys.stdin.read(256 * 1024)))
        else:
            sys.exit(main())
    except (PreviewError, OSError, ValueError, KeyError) as error:
        # CLI/private log only. HTTP errors use fixed bodies, never exceptions.
        print("Preview error: " + str(error), file=sys.stderr)
        sys.exit(1)
