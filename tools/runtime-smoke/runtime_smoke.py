#!/usr/bin/env python3
"""Runtime smoke: does a fresh Tess OS install load in each vendor CLI?

    python3 tools/runtime-smoke/runtime_smoke.py [--cli grok,kimi,...] [--install-clis] [--live]

For every selected CLI it records, per stage, PASS / FAIL / SKIPPED /
UNVERIFIED / OBSERVED:
  installed  - found on PATH, via --bin, or in a --cli-prefix
  version    - starts with a scratch HOME (no global config read or written)
  offline    - what reaches "the model" from the install, via the CLI's own
               inspect command or a local mock endpoint (no login, no model)
  live       - only with --live and only if the CLI is already signed in:
               asks "Who are you? List your commands." in the scratch install
It never logs in, never reads a vendor auth file and never edits the
operator's CLI config. See README.md for the full contract.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from clis import ADAPTERS  # noqa: E402
from smoke_lib import (FAIL, SKIPPED, ancestor_hits, command_names, fresh_home, make_nonce,  # noqa: E402
                       offline_env, run, scaffold, stage, static_checks)

REPO_ROOT = HERE.parent.parent


class Context:
    def __init__(self, args, workdir: Path):
        self.workdir = workdir
        self.path_prefix = args.node_dir
        self.bins = dict(b.split("=", 1) for b in args.bin)
        self.prefixes = [Path(p) for p in args.cli_prefix]
        self.install = self.nonce = None
        self.commands = []

    def resolve(self, binary: str):
        if binary in self.bins:
            return self.bins[binary]
        for prefix in self.prefixes:
            for cand in (prefix / "node_modules" / ".bin" / binary, prefix / binary / "node_modules" / ".bin" / binary):
                if cand.exists():
                    return str(cand)
        search = os.pathsep.join(p for p in (self.path_prefix, os.environ.get("PATH", "")) if p)
        return shutil.which(binary, path=search)


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Tess OS runtime smoke (see tools/runtime-smoke/README.md)")
    ap.add_argument("--cli", default=",".join(ADAPTERS), help="comma list of: " + ", ".join(ADAPTERS))
    ap.add_argument("--install", help="an existing scratch install to test (needs --nonce)")
    ap.add_argument("--nonce", help="the conductor name the --install was scaffolded with")
    ap.add_argument("--workdir", help="scratch directory (default: a new temp dir)")
    ap.add_argument("--bin", action="append", default=[], metavar="NAME=PATH", help="explicit CLI path")
    ap.add_argument("--cli-prefix", action="append", default=[], help="npm prefix holding node_modules/.bin")
    ap.add_argument("--node-dir", help="directory prepended to PATH for CLI runs (e.g. a Node 22 bin dir)")
    ap.add_argument("--install-clis", action="store_true", help="npm-install the npm CLIs into the workdir")
    ap.add_argument("--live", action="store_true", help="run the live prompt where the CLI is signed in")
    ap.add_argument("--json", help="write the full report here")
    return ap.parse_args(argv)


def prepare_install(args, ctx) -> dict:
    if args.install:
        if not args.nonce:
            return stage(FAIL, "--install needs --nonce (the install's conductor name)")
        ctx.install, ctx.nonce = Path(args.install).resolve(), args.nonce
        result = stage("PASS", "using existing install")
    else:
        ctx.nonce = make_nonce()
        ctx.install = ctx.workdir / "install"
        env = offline_env(fresh_home(ctx.workdir, "scaffold"), path_prefix=ctx.path_prefix)
        ok, message = scaffold(REPO_ROOT, ctx.install, ctx.nonce, env)
        result = stage("PASS" if ok else FAIL, message)
    hits = ancestor_hits(ctx.install)
    if hits:
        return stage(FAIL, "instruction files or a repo above the install would leak into the smoke: %s" % hits[:3])
    ctx.commands = command_names(ctx.install) if result["status"] == "PASS" else []
    return result


def install_clis(ctx, keys) -> dict:
    out = {}
    for key in keys:
        pkg = ADAPTERS[key].npm
        if not pkg:  # Antigravity CLI ships no npm package
            continue
        prefix = ctx.workdir / "cli" / key
        home = fresh_home(ctx.workdir, key + "-npm")
        env = offline_env(home, {"GROK_HOME": str(home / ".grok"), "npm_config_cache": str(ctx.workdir / "npm-cache")},
                          ctx.path_prefix)
        code, _o, err = run(["npm", "i", "--prefix", prefix, pkg, "--no-audit", "--no-fund"], env, ctx.workdir, 600)
        out[key] = "installed %s" % pkg if code == 0 else "npm i %s failed: %s" % (pkg, err[-200:])
        ctx.prefixes.append(prefix)
    return out


def smoke_one(ctx, key: str, live: bool) -> dict:
    cli = ADAPTERS[key](ctx)
    report = {"name": cli.name, "binary": cli.path}
    if not cli.path:
        report["installed"] = stage(SKIPPED, "`%s` not found (PATH, --bin, --cli-prefix)" % cli.binary)
        return report
    report["installed"] = stage("PASS", "found")
    report["version"] = cli.version()
    if report["version"]["status"] == FAIL:
        return report
    report.update(cli.offline())
    report["live"] = cli.live() if live else stage(SKIPPED, "pass --live to ask the real model")
    return report


def print_table(report: dict) -> None:
    print("\nTess OS runtime smoke  (install conductor: %s)" % report.get("nonce"))
    print("static: %s - %s" % (report["static"]["status"], report["static"]["detail"]))
    for key, res in report["clis"].items():
        print("\n%s (%s)" % (res["name"], res.get("binary") or "not installed"))
        for name, st in res.items():
            if isinstance(st, dict) and "status" in st:
                print("  %-11s %-10s %s" % (name, st["status"], st["detail"]))


def main(argv=None) -> int:
    args = parse_args(argv or sys.argv[1:])
    keys = [k.strip() for k in args.cli.split(",") if k.strip()]
    unknown = [k for k in keys if k not in ADAPTERS]
    if unknown:
        print("unknown --cli value(s): %s" % unknown, file=sys.stderr)
        return 2
    workdir = Path(args.workdir or tempfile.mkdtemp(prefix="tess-runtime-smoke-")).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = Context(args, workdir)
    report = {"workdir": str(workdir), "install": prepare_install(args, ctx), "nonce": ctx.nonce, "clis": {}}
    if report["install"]["status"] == FAIL:
        print("install: FAIL - %s" % report["install"]["detail"], file=sys.stderr)
        return 1
    report["static"] = static_checks(ctx.install)
    if args.install_clis:
        report["cli_installs"] = install_clis(ctx, keys)
    for key in keys:
        report["clis"][key] = smoke_one(ctx, key, args.live)
    print_table(report)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    failed = [n for n, r in report["clis"].items() for s in r.values() if isinstance(s, dict) and s.get("status") == FAIL]
    return 1 if failed or report["static"]["status"] == FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
