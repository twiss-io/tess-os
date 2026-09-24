#!/usr/bin/env bash
# Live capture smokes for the Tess brain learning loop (acceptance L3-L6, L11).
#
#   bash tests/smoke/brain_learn_live.sh <claude|codex|gemini|codex-hooks|probe> <scratch-dir> [framework-dir]
#
# Each run scaffolds a fresh instance with create-tess from <framework-dir>
# (default: this checkout) inside <scratch-dir>, drops in the fictional fixture
# brain.json (onboarding complete), holds ONE scripted conversation with the
# runtime using the operator's existing CLI login, then checks the brain on
# disk. Nothing global is written: Codex runs with a scratch CODEX_HOME whose
# auth.json is a symlink, Gemini with a scratch HOME, and the only Claude
# state touched (~/.claude/projects/<slug of the scratch instance>) is removed
# at the end. The planted token is built at run time and never committed.
# Harness-only steps (seed commit, probe push) skip git hooks; the brain tools
# themselves never do. Exit status = number of failed checks.
set -u
RT=${1:?runtime}; S=${2:?scratch dir}
FW=$(cd "${3:-$(dirname "$0")/../..}" && pwd)
PY=${PY39:-/usr/bin/python3}
GEM=${GEM:-gemini}
TOKEN=ghp_$(printf 'Q%.0s' $(seq 1 36))
SCRIPT="Decision: let's go with Postgres for the ledger. From now on, always answer in bullet points. No, that's wrong: the client's timezone is SGT, not UTC. If we went with MongoDB instead, would that be faster? Just thinking out loud. Remind me to send the pricing note to Sam by Friday. Test token: $TOKEN. Reply with just OK."
FAILS=0
mkdir -p "$S"
S=$(cd "$S" && pwd -P)

ok() { echo "PASS $*"; }
no() { echo "FAIL $*"; FAILS=$((FAILS + 1)); }
check() { local name=$1; shift; if "$@" >/dev/null 2>&1; then ok "$name"; else no "$name"; fi; }
# child runtimes must not inherit this session's Claude Code / companion variables
clean() { env $(env | sed -nE 's/^(CLAUDECODE|CLAUDE_CODE_[A-Z_]*|CLAUDE_PID|CLAUDE_EFFORT|CODEX_COMPANION_[A-Z_]*)=.*/-u \1/p') "$@"; }
slug() { printf '%s' "$1" | sed 's/[^A-Za-z0-9]/-/g'; }
tb() { (cd "$1" && shift && "$PY" scripts/brain/tessbrain.py "$@"); }

settings_local() {  # the frozen spec 9.6 lines, for a framework without ws-oobe's wiring
  "$PY" - "$1/.claude/settings.local.json" <<'EOF'
import json, sys
line = ("sh -c 'f=\"$CLAUDE_PROJECT_DIR/scripts/brain/%s\"; [ -f \"$f\" ] && "
        "exec python3 \"$f\" hook %s --runtime claude || exit 0'")
hook = lambda script, event, t, **kw: dict({"type": "command", "command": line % (script, event), "timeout": t}, **kw)
data = {"autoMemoryEnabled": False, "hooks": {
    "SessionStart": [{"matcher": "startup|resume|clear|compact",
                      "hooks": [hook("onboard.py", "session-start", 5), hook("tessbrain.py", "session-start", 5)]}],
    "UserPromptSubmit": [{"hooks": [hook("tessbrain.py", "prompt", 3)]}],
    "Stop": [{"hooks": [hook("tessbrain.py", "stop", 30, **{"async": True})]}]}}
open(sys.argv[1], "w").write(json.dumps(data, indent=1) + "\n")
EOF
}

scaffold() {  # $1 = instance dir
  node "$FW/create-tess/bin/create-tess.mjs" "$1" --yes --operator=Probe --template-source "$FW" \
    </dev/null >"$1.scaffold.log" 2>&1 || { no "scaffold $1 (see $1.scaffold.log)"; return 1; }
  mkdir -p "$1/brain" "$1/memory/projects"
  cp "$FW/tests/fixtures/brain_learn/brain.json" "$1/brain/brain.json"
  if grep -q 'tessbrain.py' "$1/.claude/settings.json" 2>/dev/null; then echo "wiring: .claude/settings.json (ws-oobe)"
  else settings_local "$1"; echo "wiring: .claude/settings.local.json (spec 9.6 lines)"; fi
  git -C "$1" config user.email probe@example.invalid  # the fixture operator's git_emails: 'probe' is typing
  git -C "$1" config user.name probe
  tb "$1" index --quiet
  git -C "$1" add -A && git -C "$1" -c user.name=p -c user.email=p@example.invalid commit -q --no-verify -m seed
}

assert_brain() {  # $1 = instance, $2 = runtime tag in the journal file name
  local D=$1 R=$2 J
  J=$(ls "$D"/brain/journal/*/*/*/*-"$R"-*.md 2>/dev/null | head -1)
  check "($R a) journal note of the conversation" grep -qF "let's go with Postgres for the ledger" "$J"
  check "($R b) lint exits 0" tb "$D" lint
  check "($R b) brain/decisions D- record: verbatim quote, source_ref resolves to it" "$PY" - "$D" <<'EOF'
import sys, glob
sys.path.insert(0, sys.argv[1] + "/scripts/brain")
from brainlib import frontmatter, lookup
from brainlib.config import Config
cfg = Config(sys.argv[1])
recs = [frontmatter.read(p)[0] for p in glob.glob(sys.argv[1] + "/brain/decisions/D-*.md")]
recs = [m for m in recs if m.get("source_quote") == "let's go with Postgres for the ledger"]
line = lookup.resolve(cfg, recs[0]["source_ref"])
sys.exit(0 if line and recs[0]["source_quote"] in line.text else 1)
EOF
  check "($R c) profile.md has the preference" grep -q "bullet points" "$D/brain/profile.md"
  check "($R c) correction record" sh -c "grep -lF \"the client's timezone is SGT, not UTC\" '$D'/brain/profile/C-*.md"
  check "($R d) no MongoDB decision" sh -c "! grep -rl MongoDB '$D/brain/decisions'"
  check "($R e) planted token absent" sh -c "! grep -rsF '$TOKEN' '$D/brain' '$D/.tess/state/brain'"
  check "($R e) journal redacted" grep -rq '<REDACTED:' "$D/brain/journal"
  check "($R f) learned.md >= 3 entries" sh -c "[ \$(grep -c '^- 20' '$D/brain/learned.md') -ge 3 ]"
  check "($R f) proposed pricing-note loop" sh -c "grep -l 'pricing note' '$D'/brain/loops/L-*.md | xargs grep -l 'status: \"proposed\"'"
}

run_claude() {
  local D="$S/claude-fx"; scaffold "$D" || return
  (cd "$D" && clean CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 claude -p "$SCRIPT" --model haiku \
     --setting-sources project,local </dev/null >"$S/l3-claude.out" 2>&1)
  echo "claude replied: $(head -c 200 "$S/l3-claude.out")"
  for _ in $(seq 1 60); do grep -qsF "Postgres for the ledger" "$D"/brain/journal/*/*/*/*-claude-*.md && break; sleep 1; done
  check "(L3) async Stop hook journaled without a manual sync" sh -c "grep -qsF 'Postgres for the ledger' '$D'/brain/journal/*/*/*/*-claude-*.md"
  tb "$D" sync --quiet
  assert_brain "$D" claude
  (cd "$D" && clean TESS_BRAIN_TEST_NONCE=LEARN-NONCE-3K claude -p 'List every token matching [A-Z]+-NONCE-[A-Z0-9]+ that you can see.' \
     --model haiku --setting-sources project,local --no-session-persistence </dev/null >"$S/l3-nonce.out" 2>&1)
  check "(L3 g) SessionStart snapshot reaches the model" grep -q LEARN-NONCE-3K "$S/l3-nonce.out"
  rm -rf "$HOME/.claude/projects/$(slug "$D")"
}

codex_home() {  # $1 = CODEX_HOME, $2 = trusted project (optional)
  mkdir -p "$1"; ln -sf "$HOME/.codex/auth.json" "$1/auth.json"
  printf 'model = "gpt-5.5"\n' > "$1/config.toml"
  [ -n "${2:-}" ] && printf '\n[projects."%s"]\ntrust_level = "trusted"\n' "$2" >> "$1/config.toml"
  return 0
}

run_codex() {
  local D="$S/codex-fx"; scaffold "$D" || return
  codex_home "$S/ch"
  (cd "$D" && clean CODEX_HOME="$S/ch" codex exec -m gpt-5.5 -s read-only "$SCRIPT" </dev/null >"$S/l4-codex.out" 2>&1)
  echo "codex replied: $(tail -c 200 "$S/l4-codex.out")"
  (cd "$D" && CODEX_HOME="$S/ch" "$PY" scripts/brain/tessbrain.py sync --runtime codex --quiet)
  assert_brain "$D" codex
  rm -rf "$S/ch"
}

run_gemini() {
  local D="$S/gemini-fx"; scaffold "$D" || return
  if [ -z "${GEMINI_API_KEY:-}" ]; then no "(L5) GEMINI_API_KEY not set: Gemini capture UNVERIFIED"; return; fi
  mkdir -p "$S/gh"
  (cd "$D" && clean HOME="$S/gh" GEMINI_CLI_TRUST_WORKSPACE=true "$GEM" -p "$SCRIPT" </dev/null >"$S/l5-gemini.out" 2>&1)
  (cd "$D" && HOME="$S/gh" "$PY" scripts/brain/tessbrain.py sync --runtime gemini --quiet)
  local J; J=$(ls "$D"/brain/journal/*/*/*/*-gemini-*.md 2>/dev/null | head -1)
  check "(L5 a) gemini journal note" grep -qF "let's go with Postgres for the ledger" "$J"
  check "(L5 b) decision with verbatim quote" sh -c "grep -lF 'Postgres for the ledger' '$D'/brain/decisions/D-*.md"
  check "(L5 b) lint exits 0" tb "$D" lint
  check "(L5 e) planted token absent" sh -c "! grep -rsF '$TOKEN' '$D/brain' '$D/.tess/state/brain'"
  rm -rf "$S/gh"
}

run_codex_hooks() {  # L6: trusted project + hook bypass flag; capture with no manual sync
  local D="$S/codexhooks-fx"; scaffold "$D" || return
  codex_home "$S/chh" "$D"
  mkdir -p "$D/brain/sub"
  local q='List every token matching [A-Z]+-NONCE-[A-Z0-9]+ that you can see.'
  for dir in "$D" "$D/brain/sub"; do
    (cd "$dir" && clean TESS_BRAIN_TEST_NONCE=LEARN-NONCE-6X CODEX_HOME="$S/chh" codex exec -m gpt-5.5 -s read-only \
       --dangerously-bypass-hook-trust "$q" </dev/null >"$S/l6-$(basename "$dir").out" 2>&1)
    check "(L6) SessionStart nonce from $(basename "$dir")" grep -q LEARN-NONCE-6X "$S/l6-$(basename "$dir").out"
  done
  for _ in $(seq 1 30); do ls "$D"/brain/journal/*/*/*/*-codex-*.md >/dev/null 2>&1 && break; sleep 1; done
  check "(L6) codex journal written by the Stop hook (no manual sync)" sh -c "ls '$D'/brain/journal/*/*/*/*-codex-*.md"
  rm -rf "$S/chh"
}

ask() {  # $1 runtime, $2 clone, $3 question, $4 output file
  case $1 in
    claude) (cd "$2" && clean claude -p --no-session-persistence --setting-sources project,local "$3" </dev/null >"$4" 2>&1) ;;
    codex) (cd "$2" && clean codex exec --ephemeral --ignore-user-config -m gpt-5.5 -s read-only "$3" </dev/null >"$4" 2>&1) ;;
  esac
}

run_probe() {  # L11, after run_claude: can a zero-context agent answer from files alone?
  local D="$S/claude-fx"
  [ -d "$D/brain/journal" ] || { no "(L11) run the claude smoke first"; return; }
  git -C "$D" add brain memory/projects
  git -C "$D" -c user.name=p -c user.email=p@example.invalid commit -q -m probe || no "(L11) gate refused the probe commit"
  rm -rf "$S/p.git" "$S/zc" "$S/zc0"; git init -q --bare "$S/p.git"
  git -C "$D" push -q --no-verify "$S/p.git" HEAD:main
  git clone -q "$S/p.git" "$S/zc"; git clone -q "$S/p.git" "$S/zc0" && git -C "$S/zc0" checkout -q HEAD~1
  local Q1="What did the operator decide about the ledger database? Quote it and give the file path."
  local Q2="How does the operator want answers formatted?"
  local Q3="Did the operator decide to use MongoDB? Answer yes or no first."
  local Q4="What open loops exist?"
  local Q5="Where is the note of the conversation that set these?"
  for rt in claude codex; do
    local i=0; for q in "$Q1" "$Q2" "$Q3" "$Q4" "$Q5"; do i=$((i + 1)); ask $rt "$S/zc" "$q" "$S/l11-$rt-q$i.out" & done
  done
  ask claude "$S/zc0" "$Q1" "$S/l11-neg-q1.out" &
  wait
  for rt in claude codex; do
    local n=0 q3=0
    grep -qi postgres "$S/l11-$rt-q1.out" && grep -q 'brain/decisions/' "$S/l11-$rt-q1.out" && n=$((n + 1))
    grep -qi bullet "$S/l11-$rt-q2.out" && n=$((n + 1))
    sed -n '/[A-Za-z]/{p;q;}' "$S/l11-$rt-q3.out" | grep -qiE '^[^A-Za-z]*no\b' && { n=$((n + 1)); q3=1; }
    grep -qi 'pricing note' "$S/l11-$rt-q4.out" && n=$((n + 1))
    grep -q 'brain/journal/' "$S/l11-$rt-q5.out" && n=$((n + 1))
    echo "L11 $rt: $n/5 correct (Q3 mandatory: $q3)"
    if [ $n -ge 4 ] && [ $q3 -eq 1 ]; then ok "(L11) $rt zero-context probe"; else no "(L11) $rt zero-context probe"; fi
  done
  check "(L11) negative control: pre-conversation clone cannot answer Q1" sh -c "! grep -qi postgres '$S/l11-neg-q1.out'"
}

case $RT in
  claude) run_claude ;; codex) run_codex ;; gemini) run_gemini ;; codex-hooks) run_codex_hooks ;; probe) run_probe ;;
  *) echo "unknown runtime $RT"; exit 2 ;;
esac
echo "brain_learn_live $RT: $FAILS failure(s)"
exit $FAILS
