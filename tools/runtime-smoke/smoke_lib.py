"""Shared helpers for the runtime smoke (stdlib only; Python 3.9+).

Safety rules every helper follows:
  * A CLI never runs with the operator's HOME during an offline stage. Each
    run gets a fresh scratch HOME (and the CLI's own *_HOME variable), so no
    global CLI config is read or written.
  * Provider credentials in the environment are removed before an offline
    stage, so a stray key can never turn a mock run into a real model call.
  * Nothing here opens, reads, copies or prints a vendor login file. Whether a
    CLI is signed in is asked of the CLI itself (see clis.py).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

PROMPT = "Who are you? List your commands."

# Environment variables that could route a run to a real provider. Offline
# stages delete them; values are never read or logged.
PROVIDER_ENV = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL", "XAI_API_KEY",
    "GROK_CODE_XAI_API_KEY", "KIMI_API_KEY", "KIMI_BASE_URL", "GEMINI_API_KEY",
    "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI", "DASHSCOPE_API_KEY",
    "BAILIAN_CODING_PLAN_API_KEY", "DEEPSEEK_API_KEY",
)

# Instruction-file budgets documented by the runtimes (see adapters/CONFORMANCE.md).
AGENTS_MD_BUDGETS = {
    "Devin Desktop workspace rule (characters)": 12000,
    "Codex AGENTS.md chain": 32 * 1024,
    "Kimi Code recommended AGENTS.md total": 32 * 1024,
}
DSH_BASELINE_BUDGET = 65536  # DeepSeek Harness base profile: AGENTS.md + CLAUDE.md together

ANCESTOR_MARKERS = ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md", "GEMINI.md", "QWEN.md", ".git")

PASS, FAIL, SKIPPED, UNVERIFIED, OBSERVED = "PASS", "FAIL", "SKIPPED", "UNVERIFIED", "OBSERVED"


def stage(status: str, detail: str, **facts) -> dict:
    """One stage result. FAIL is the only status that fails the run."""
    out = {"status": status, "detail": detail}
    out.update(facts)
    return out


def run(cmd, env: dict, cwd: Path, timeout: int = 180) -> tuple:
    """Run a command without a TTY. Returns (exit code or None on timeout, stdout, stderr)."""
    try:
        proc = subprocess.run([str(c) for c in cmd], env=env, cwd=str(cwd), capture_output=True,
                              text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        return None, _text(exc.stdout), _text(exc.stderr)
    except OSError as exc:
        return 127, "", str(exc)


def _text(value) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def offline_env(scratch_home: Path, extra: dict = None, path_prefix: str = None) -> dict:
    """os.environ with HOME redirected and every provider credential removed."""
    env = {k: v for k, v in os.environ.items() if k not in PROVIDER_ENV}
    env["HOME"] = str(scratch_home)
    env.pop("XDG_CONFIG_HOME", None)
    env.pop("XDG_DATA_HOME", None)
    if path_prefix:
        env["PATH"] = path_prefix + os.pathsep + env.get("PATH", "")
    env.update(extra or {})
    return env


def fresh_home(workdir: Path, name: str) -> Path:
    home = workdir / "homes" / name
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    return home


def ancestor_hits(path: Path) -> list:
    """Instruction files or repos above `path` that a CLI walking upward could load."""
    hits = []
    for parent in Path(path).resolve().parents:
        for marker in ANCESTOR_MARKERS:
            if (parent / marker).exists():
                hits.append(str(parent / marker))
    return hits


def make_nonce() -> str:
    return "Smoke" + secrets.token_hex(3)


def scaffold(repo_root: Path, dest: Path, nonce: str, env: dict) -> tuple:
    """Create a fresh install with create-tess from this checkout. Returns (ok, message)."""
    cli = repo_root / "create-tess" / "bin" / "create-tess.mjs"
    if not (repo_root / "create-tess" / "node_modules").is_dir():
        return False, "create-tess dependencies missing: run `npm --prefix create-tess ci` first"
    cmd = ["node", str(cli), str(dest), "--yes", "--operator=SmokeOperator", "--conductor=" + nonce,
           "--vibe=studio", "--path=builders", "--pathway=co-founder", "--no-gate-hooks"]
    code, out, err = run(cmd, env, dest.parent, timeout=300)
    if code != 0 or not (dest / "AGENTS.md").is_file():
        return False, "create-tess exited %s: %s" % (code, (err or out)[-400:])
    return True, "scaffolded with conductor " + nonce


def command_names(install: Path) -> list:
    """The Tess commands as rendered skills (.agents/skills/tess-<name>)."""
    root = install / ".agents" / "skills"
    return sorted(p.name[len("tess-"):] for p in root.glob("tess-*") if (p / "SKILL.md").is_file())


def distinctive_line(text: str, other: str) -> str:
    """A long line of `text` that `other` does not contain: a fingerprint for 'this file loaded'."""
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 60 and line not in other:
            return line[:60]
    return ""


def request_text(body: dict) -> str:
    """Flatten every message of a captured Chat Completions request into one string."""
    parts = []
    for msg in body.get("messages") or []:
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif content is not None:
            parts.append(json.dumps(content))
    return "\n".join(parts)


def analyse_requests(bodies: list, install: Path, nonce: str) -> dict:
    """What reached the model: the richest captured request decides."""
    agents = (install / "AGENTS.md").read_text(encoding="utf-8")
    claude_path = install / "CLAUDE.md"
    claude = claude_path.read_text(encoding="utf-8") if claude_path.is_file() else ""
    agents_mark, claude_mark = distinctive_line(agents, claude), distinctive_line(claude, agents)
    commands = command_names(install)
    best = {"requests": len(bodies), "nonce_hits": 0, "skills_listed": 0, "commands": len(commands),
            "agents_md_loaded": False, "claude_md_loaded": False}
    for body in bodies:
        text = request_text(body)
        listed = sum(1 for c in commands if ("tess-" + c) in text)
        if (text.count(nonce), listed) > (best["nonce_hits"], best["skills_listed"]):
            best.update(nonce_hits=text.count(nonce), skills_listed=listed,
                        agents_md_loaded=bool(agents_mark) and agents_mark in text,
                        claude_md_loaded=bool(claude_mark) and claude_mark in text)
    return best


def judge_load(facts: dict) -> dict:
    """PASS when the conductor's name and (nearly) every command reached the model."""
    ok = facts["nonce_hits"] > 0 and facts["skills_listed"] >= max(1, facts["commands"] - 2)
    loaded = [n for n, k in (("AGENTS.md", "agents_md_loaded"), ("CLAUDE.md", "claude_md_loaded")) if facts[k]]
    detail = "loaded %s; conductor name seen %d time(s); %d/%d tess-* skills listed" % (
        " + ".join(loaded) or "no instruction file", facts["nonce_hits"], facts["skills_listed"], facts["commands"])
    return stage(PASS if ok else FAIL, detail, **facts)


def judge_reply(reply: str, nonce: str, commands: list) -> dict:
    """Live check: the answer names the conductor and at least three of its commands."""
    named = sorted({c for c in commands if re.search(r"(?<![\w-])(tess-)?%s(?![\w-])" % re.escape(c), reply)})
    ok = nonce in reply and len(named) >= 3
    detail = "reply %s the conductor name; names %d command(s)" % ("contains" if nonce in reply else "lacks", len(named))
    return stage(PASS if ok else FAIL, detail, commands_named=named[:10], reply_excerpt=reply.strip()[:800])


def static_checks(install: Path) -> dict:
    """Files the AGENTS.md-reading CLIs rely on exist and fit the documented budgets."""
    problems = []
    agents = install / "AGENTS.md"
    size = agents.stat().st_size if agents.is_file() else -1
    if size < 0:
        problems.append("AGENTS.md missing")
    for label, limit in AGENTS_MD_BUDGETS.items():
        if size > limit:
            problems.append("AGENTS.md exceeds %s (%d)" % (label, limit))
    claude = install / "CLAUDE.md"
    pair = size + (claude.stat().st_size if claude.is_file() else 0)
    if pair > DSH_BASELINE_BUDGET:
        problems.append("AGENTS.md + CLAUDE.md exceed the DeepSeek Harness baseline budget")
    skills = command_names(install)
    for name in skills:
        head = (install / ".agents" / "skills" / ("tess-" + name) / "SKILL.md").read_text(encoding="utf-8")[:600]
        if not (head.startswith("---") and "\nname:" in head and "\ndescription:" in head):
            problems.append("tess-%s/SKILL.md lacks name/description frontmatter" % name)
    if not skills:
        problems.append("no .agents/skills/tess-*/SKILL.md rendered")
    detail = "AGENTS.md within every documented budget; %d skills with name+description" % len(skills)
    return stage(FAIL if problems else PASS, "; ".join(problems) or detail, skills=len(skills))
