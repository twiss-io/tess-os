#!/usr/bin/env bash
# Live-model smoke for self-starting onboarding (acceptance O9, O10, O11).
#
#   bash tests/smoke/brain_oobe_live.sh claude|codex|gemini|all <scratch-dir>
#
# Uses the operator's EXISTING CLI login; writes no global config. Every
# scaffold, transcript and temporary HOME lives under <scratch-dir>:
#   <scratch>/live-<rt>-fresh   un-onboarded create-tess scaffold
#   <scratch>/live-<rt>-done    onboarded scaffold (negative control)
#   <scratch>/smoke/<rt>-*.txt  every model reply, verbatim
# Env: GEM=<gemini binary> (default: gemini on PATH), CLAUDE_MODEL (haiku),
# CODEX_MODEL (gpt-5.5), SMOKE_TIMEOUT seconds per call (300).
# Each model-level check (hi, task-first, identity) is reported as "k of 3 runs" and
# passes at k >= 2; exit 1 if any check fails.
set -u
RT="${1:-}"; S="${2:-}"
if [ -z "$RT" ] || [ -z "$S" ]; then echo "usage: $0 claude|codex|gemini|all <scratch-dir>" >&2; exit 2; fi
WT="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$S/smoke"; S="$(cd "$S" && pwd)"
Q1='who is this brain for|personal.*agency.*organi[sz]ation'
TO="${SMOKE_TIMEOUT:-300}"
FAILED=0

pass() { echo "PASS $*"; }
fail() { echo "FAIL $*"; FAILED=1; }
flat() { tr '\n' ' ' < "$1"; }
limit() { perl -e 'alarm shift; exec @ARGV or die "exec: $!"' "$TO" "$@"; }

yaml_python_path() {  # put a PyYAML-capable python3 first on PATH (tessctl needs it)
  for py in python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import yaml' 2>/dev/null; then
      export PATH="$(dirname "$(command -v "$py")"):$PATH"; return 0
    fi
  done
  echo "note: no PyYAML python3 found; create-tess may fail" >&2
}

scaffold() {  # scaffold <dir> [onboard]
  local dir="$1"
  [ -d "$dir" ] && return 0
  HOME="$S/ct-home" node "$WT/create-tess/bin/create-tess.mjs" "$dir" --yes --operator Probe \
    --conductor Tess --vibe command --path founders --pathway chief-of-staff > "$dir.create.log" 2>&1 \
    || { fail "create-tess $dir (see $dir.create.log)"; return 1; }
  if [ "${2:-}" = onboard ]; then
    (cd "$dir" && python3 scripts/brain/onboard.py init --non-interactive \
       --answers "$WT/tests/fixtures/brain_oobe/answers-agency-solo.json" >/dev/null \
     && python3 scripts/brain/onboard.py apply >/dev/null) || { fail "onboard $dir"; return 1; }
  fi
}

count_q1() {  # count_q1 <prefix> -> replies matching Q1 and naming Tess
  local n=0 f
  for f in "$1"-*.txt; do
    if flat "$f" | grep -Eiq "$Q1" && grep -q 'Tess' "$f"; then n=$((n + 1)); fi
  done
  echo "$n"
}

count_q1_only() {
  local n=0 f
  for f in "$1"-*.txt; do flat "$f" | grep -Eiq "$Q1" && n=$((n + 1)); done
  echo "$n"
}

claude_ask() {  # claude_ask <dir> <out> <prompt>
  (cd "$1" && CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 TESS_BRAIN_TEST_NONCE=OOBE-NONCE-7Q limit claude -p "$3" \
     --model "${CLAUDE_MODEL:-haiku}" --setting-sources project,local --no-session-persistence \
     < /dev/null > "$2" 2> "$2.err")
}

codex_ask() {
  (cd "$1" && limit codex exec --ephemeral --ignore-user-config -m "${CODEX_MODEL:-gpt-5.5}" -s read-only \
     "$3" < /dev/null > "$2" 2> "$2.err")
}

gemini_ask() {
  mkdir -p "$S/ghome"
  (cd "$1" && HOME="$S/ghome" GEMINI_CLI_TRUST_WORKSPACE=true limit "${GEM:-gemini}" -p "$3" \
     < /dev/null > "$2" 2> "$2.err")
}

three_hi() {  # three_hi <rt> <dir> <prefix>
  local i
  for i in 1 2 3; do "$1_ask" "$2" "$3-$i.txt" "hi"; done
}

TASK='Can you summarise what this repo is in two sentences?'
IDENT='Before we start: what is your name, and name three slash commands or skills you have here?'

task_first() {  # task_first <rt> <dir> <prefix> <label>: a real task as the first message
  local i k
  for i in 1 2 3; do "$1_ask" "$2" "$3-$i.txt" "$TASK"; done
  k=$(count_q1 "$3"); [ "$k" -ge 2 ] && pass "$4 task-first onboarding: $k of 3" || fail "$4 task-first onboarding: $k of 3"
}

ident_ok() {  # ident_ok <rt> <file>: the spec's identity + commands assertion, as written
  grep -q Tess "$2" || return 1
  if [ "$1" = claude ]; then  # O9: 'Tess' and >=2 of /add-mission|/wake|/close|/help|brain-onboard
    [ "$(grep -Eo '/add-mission|/wake|/close|/help|brain-onboard' "$2" | sort -u | wc -l | tr -d ' ')" -ge 2 ]
  else  # O10: 'Tess' AND 'brain-onboard' AND >=1 real 'tess-' skill (all three, not either)
    grep -q 'brain-onboard' "$2" && grep -Eq 'tess-(wake|help|close|add-mission|summary)' "$2"
  fi
}

identity() {  # identity <rt> <dir> <prefix> <label>: k of 3 single calls
  local i k=0
  for i in 1 2 3; do
    "$1_ask" "$2" "$3-$i.txt" "$IDENT"
    if ident_ok "$1" "$3-$i.txt"; then k=$((k + 1)); echo "  run $i: pass"; else echo "  run $i: FAIL ($3-$i.txt)"; fi
  done
  [ "$k" -ge 2 ] && pass "$4 identity + commands/skills: $k of 3" || fail "$4 identity + commands/skills: $k of 3"
}

smoke_claude() {
  command -v claude >/dev/null || { fail "claude CLI not on PATH"; return; }
  local fresh="$S/live-claude-fresh" onb="$S/live-claude-done" o="$S/smoke/claude"
  scaffold "$fresh" && scaffold "$onb" onboard || return
  three_hi claude "$fresh" "$o-hi"
  local k; k=$(count_q1 "$o-hi"); [ "$k" -ge 2 ] && pass "O9 claude onboarding: $k of 3" || fail "O9 claude onboarding: $k of 3"
  task_first claude "$fresh" "$o-task" O9
  identity claude "$fresh" "$o-ident" O9
  claude_ask "$fresh" "$o-nonce.txt" 'List every token matching [A-Z]+-NONCE-[A-Z0-9]+ that you can see.'
  grep -q 'OOBE-NONCE-7Q' "$o-nonce.txt" && pass "O9 claude hook visibility (nonce seen)" || fail "O9 claude hook visibility"
  three_hi claude "$onb" "$o-neg"
  k=$(count_q1_only "$o-neg"); [ "$k" -eq 0 ] && pass "O9 claude negative control: 0 of 3" || fail "O9 claude negative control: $k of 3 asked Q1"
}

smoke_codex() {
  command -v codex >/dev/null || { fail "codex CLI not on PATH"; return; }
  local fresh="$S/live-codex-fresh" onb="$S/live-codex-done" o="$S/smoke/codex"
  scaffold "$fresh" && scaffold "$onb" onboard || return
  three_hi codex "$fresh" "$o-hi"
  local k; k=$(count_q1 "$o-hi"); [ "$k" -ge 2 ] && pass "O10 codex onboarding: $k of 3" || fail "O10 codex onboarding: $k of 3"
  task_first codex "$fresh" "$o-task" O10
  identity codex "$fresh" "$o-ident" O10
  three_hi codex "$onb" "$o-neg"
  k=$(count_q1_only "$o-neg"); [ "$k" -eq 0 ] && pass "O10 codex negative control: 0 of 3" || fail "O10 codex negative control: $k of 3 asked Q1"
}

smoke_gemini() {
  local gem="${GEM:-gemini}" fresh="$S/live-gemini-fresh" o="$S/smoke/gemini"
  command -v "$gem" >/dev/null || { fail "gemini CLI not found (set GEM=)"; return; }
  echo "gemini --version: $("$gem" --version 2>/dev/null)"
  scaffold "$fresh" || return
  # GEMINI.md (rendered by the gemini target) ends with the import line; it sits
  # at line 17 of 17 in v0.2.0, so the check reads the whole file, not a head.
  echo "GEMINI.md import line: $(grep -n '^@./AGENTS.md$' "$fresh/GEMINI.md" | cut -d: -f1) of $(wc -l < "$fresh/GEMINI.md" | tr -d ' ')"
  (cd "$fresh" && grep -qx '@./AGENTS.md' GEMINI.md && grep -q '## Second brain: read this first' AGENTS.md \
    && python3 - .agents/skills/brain-onboard/SKILL.md <<'PY'
import sys
text = open(sys.argv[1]).read()
assert text.startswith("---\n"), "no front matter"
fm = dict(l.split(":", 1) for l in text[4:].split("\n---", 1)[0].splitlines() if ":" in l)
assert fm["name"].strip() == "brain-onboard" and fm["description"].strip()
PY
  ) && pass "O11 gemini config (GEMINI.md import, BOOT in AGENTS.md, skill front matter)" || fail "O11 gemini config"
  if [ -z "${GEMINI_API_KEY:-}" ]; then echo "Gemini model-level smoke: UNVERIFIED (no auth)"; return; fi
  three_hi gemini "$fresh" "$o-hi"
  local k; k=$(count_q1 "$o-hi"); [ "$k" -ge 2 ] && pass "O11 gemini onboarding: $k of 3" || fail "O11 gemini onboarding: $k of 3"
  task_first gemini "$fresh" "$o-task" O11
}

yaml_python_path
case "$RT" in
  claude) smoke_claude ;;
  codex) smoke_codex ;;
  gemini) smoke_gemini ;;
  all) smoke_claude; smoke_codex; smoke_gemini ;;
  *) echo "unknown runtime $RT" >&2; exit 2 ;;
esac
echo "transcripts: $S/smoke/"
exit "$FAILED"
