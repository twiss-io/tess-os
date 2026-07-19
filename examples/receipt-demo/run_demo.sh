#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
#
# Runs the Agent Receipt demo: propose -> approve -> sign -> journal -> verify,
# using ephemeral, test-only GPG keys (never committed, never registered).
# See README.md in this directory for what this proves.
set -euo pipefail

if ! command -v gpg >/dev/null 2>&1; then
  echo "This demo requires the 'gpg' binary (used only for ephemeral, test-only keys)." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/build_demo.py"
