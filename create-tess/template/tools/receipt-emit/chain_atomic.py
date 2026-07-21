# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""Atomic, verify-BEFORE-commit chain append for tools/receipt-emit.

The chain file (`--chain`) is the ONLY thing this tool ever writes anywhere.
Every write goes through `append_receipt_atomically`:

  1. Read the existing chain file's bytes (treated as empty if the file
     does not exist yet — the new receipt becomes the genesis line).
  2. Build the CANDIDATE full file content: existing bytes + exactly one
     new JSON line.
  3. Write the candidate content to a fresh temp file in the SAME
     directory as `--chain` (`tempfile.mkstemp(dir=...)`), so the final
     rename is a same-filesystem, atomic `os.replace` on every POSIX
     filesystem this repository targets — never a cross-filesystem copy.
  4. Call `verify_fn(temp_path)` — `receipt_emit.py` wires this to a REAL
     subprocess call into `tools/receipt-verify/receipt_verify.py
     verify-chain`, run against the CANDIDATE file, BEFORE it ever
     becomes the real `--chain` file (see docs/AGENT_RECEIPT_SPEC.md
     "Self-verify"). `verify_fn` raises `errors.EmitRefused` on any
     failure.
  5. Only once `verify_fn` returns cleanly does `os.replace(temp_path,
     chain_path)` run — an atomic rename. A reader of `chain_path` at any
     instant during this process sees EITHER the complete old file or the
     complete new file; there is no instant at which it can observe a
     partial line.
  6. On ANY failure at any step — read, write, verify-fn raising, or an
     injected/simulated crash — the temp file is unlinked and the
     ORIGINAL chain file is left byte-for-byte untouched. No partial
     line and no orphaned temp file survives a failed or interrupted run.

This is deliberately STRONGER than "append, then verify, then roll back on
failure": a candidate that fails self-verify can never even briefly become
part of the committed chain, because the real file is never touched until
AFTER the candidate has already verified clean.

★ KNOWN LIMITATION — no concurrent-writer lock. Two `receipt_emit.py emit`
invocations racing against the SAME `--chain` file can both read the same
"last line," compute the same `(sequence, prev_hash)`, and then each
independently win their own atomic rename — the second `os.replace` fully
overwrites the first receipt's line, silently losing it (last-writer-wins,
not a corrupted/partial file, but a real dropped receipt). This module
guarantees no PARTIAL line and no orphaned temp file even under a crash;
it does NOT guarantee mutual exclusion between concurrent emitters onto
the same chain file. `.tess/state/tasks/**`'s own per-task advisory
`flock` (`docs/STATE_LAYER.md`) is the precedent for how this repository
already solves exactly this class of problem — adding the same discipline
here is a natural, scoped follow-on, deliberately left out of this PR
rather than silently assumed away. A single-writer-at-a-time operating
model (one emit at a time, e.g. serialized by CI or a human operator) is
safe today without it.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from errors import EmitRefused


def read_existing_chain_text(chain_path: Path) -> str:
    try:
        return chain_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def next_chain_link(chain_path: Path, receipt_content_hash_fn) -> tuple[int, str]:
    """(sequence, prev_receipt_hash) for the NEXT receipt to append, derived
    from the LAST line of the existing chain file — `(0, "GENESIS")` if the
    file is missing or empty. `receipt_content_hash_fn` is
    `canonical.receipt_content_hash`, injected rather than imported
    directly so this module has no hard dependency on where
    tools/receipt-verify/ lives on disk."""
    text = read_existing_chain_text(chain_path)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return 0, "GENESIS"
    try:
        last_receipt = json.loads(lines[-1])
    except json.JSONDecodeError as e:
        raise EmitRefused([f"the last line of {chain_path} is not valid JSON: {e}"])
    last_sequence = (last_receipt.get("chain") or {}).get("sequence")
    if not isinstance(last_sequence, int):
        raise EmitRefused([
            f"the last line of {chain_path} has no valid chain.sequence — "
            f"refusing to append onto a malformed chain file"
        ])
    return last_sequence + 1, receipt_content_hash_fn(last_receipt)


def append_receipt_atomically(chain_path: Path, new_receipt: dict, verify_fn) -> None:
    """Appends exactly one JSON line for `new_receipt` to `chain_path`,
    verifying the CANDIDATE file via `verify_fn` before it is ever
    committed. Raises `EmitRefused` (propagated from `verify_fn`) or any
    OSError encountered along the way; in every failure case, `chain_path`
    is left exactly as it was found and no temp file is left behind."""
    chain_path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = read_existing_chain_text(chain_path)
    new_line = json.dumps(new_receipt, sort_keys=True) + "\n"
    if existing_text and not existing_text.endswith("\n"):
        existing_text += "\n"
    candidate_text = existing_text + new_line

    fd, tmp_name = tempfile.mkstemp(
        prefix=".receipt-emit-", suffix=".tmp", dir=str(chain_path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(candidate_text)
            f.flush()
            os.fsync(f.fileno())
        verify_fn(tmp_path)
        os.replace(str(tmp_path), str(chain_path))
    except BaseException:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise
