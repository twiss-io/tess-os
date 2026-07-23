#!/usr/bin/env bash
# record-demo.sh — regenerates docs/demo/tess-demo.cast + .svg from scratch.
#
# Two real, unmodified beats, run end to end with no hand-edited output:
#   1. the create-tess wizard, driven through its five axes (vibe, name,
#      starter path, conductor name, pathway) by driver.py over a real pty
#   2. the Agent Receipt "show me the receipt" demo (propose -> approve ->
#      sign -> journal -> verify -> tamper-rejection), via `make receipt-demo`
#
# Requires: python3, node (with create-tess/ deps installed via
# `npm install` in create-tess/), asciinema (`pip install asciinema`), gpg,
# and network access for the one-shot `npx svg-term-cli` conversion step.
#
# NOTE: pty.fork() (used by driver.py) leaves the pty with no window size
# set, which breaks width-sensitive rendering (every character lands on its
# own line) -- driver.py works around this by setting a real winsize via
# TIOCSWINSZ immediately after fork. If you adapt this script, keep that.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${REPO_ROOT}/docs/demo"
WORK_DIR="$(mktemp -d)"
TARGET_DIR="${WORK_DIR}/my-os"
ASCIINEMA="${ASCIINEMA_BIN:-asciinema}"

trap 'rm -rf "$WORK_DIR"' EXIT

cat > "${WORK_DIR}/session.sh" <<SESSION
set -euo pipefail
cd "${REPO_ROOT}"
echo '\$ node create-tess/bin/create-tess.mjs my-os'
sleep 1
python3 "${OUT_DIR}/driver.py" node create-tess/bin/create-tess.mjs "${TARGET_DIR}"

sleep 1.5
echo
echo '\$ make receipt-demo    # show me the receipt'
sleep 1
make receipt-demo

sleep 1.5
SESSION

"$ASCIINEMA" rec --overwrite --cols 100 --rows 32 -i 2 \
  --title "Tess OS -- create-tess wizard + Agent Receipt demo" \
  --command "bash '${WORK_DIR}/session.sh'" \
  "${OUT_DIR}/tess-demo.cast"

cat "${OUT_DIR}/tess-demo.cast" \
  | npx --yes svg-term-cli --out "${OUT_DIR}/tess-demo.svg" --window --width 100 --height 32 --padding 16

echo "wrote ${OUT_DIR}/tess-demo.cast and ${OUT_DIR}/tess-demo.svg"
