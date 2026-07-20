# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Twiss
"""Shared refusal exception for tools/receipt-emit.

A single, uniform way every stage of the emit pipeline (decision-shape
check, policy lookup, GPG operations, chain self-verify) signals a
fail-closed refusal — never a partial write, never a bare exception with no
caller-facing reason. Mirrors tools/receipt-verify/checks.py's own
"return a list of reasons" discipline, but as an exception: emit is a
write pipeline with a single all-or-nothing outcome (a receipt is
committed or it is not), not a read-only checker that always wants to keep
running and collect every possible issue at once.
"""

from __future__ import annotations


class EmitRefused(Exception):
    """Raised the moment ANY check fails, at any stage. Every raise site in
    this tool is BEFORE the one write this tool performs
    (chain_atomic.append_receipt_atomically) — see that module's own header
    for why a refusal here always leaves --chain byte-for-byte untouched."""

    def __init__(self, reasons):
        if isinstance(reasons, str):
            reasons = [reasons]
        self.reasons = list(reasons)
        super().__init__("; ".join(self.reasons) or "refused (no reason given)")
