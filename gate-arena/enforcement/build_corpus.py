#!/usr/bin/env python3
"""
gate-arena/enforcement/build_corpus.py — materializes the Layer B seeded
diff corpus (`corpus/<case>/`) from the definitions below.

12 cases = 6 domains x {good, bad}. Every "bad" case is a diff that LOOKS
like a plausible fix (same shape, same intent, subtly wrong) — not a
strawman. Every ground-truth label is verified empirically by
`test_grader.py` inside each case dir, not asserted by construction alone:
run `python3 -m pytest gate-arena/enforcement/corpus -q` after building to
confirm every "good" grader passes and every "bad" grader fails (i.e. the
grader actually detects the planted defect).

Committed AFTER gate-arena/PRE_REGISTERED_CAVEAT.md (check git log) — the
corpus content itself is not a "result," but the caveat's rule that
selection bias should be disclosed applies to it: these are seeded,
known-shape bugs (drawn from the same bug classes proving-ground's tasks
11-19 already used — rounding, CSV quoting, path traversal, mass
assignment, idempotency, discount-spec caps), not organically-occurring
production subtleties.
"""

from __future__ import annotations

import json
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"

CASES = {
    # ------------------------------------------------------------------
    "01-rounding": {
        "domain": "billing / currency rounding",
        "brief": """# Bug report: `round_currency` rounds invoice line items incorrectly

`round_currency(amount, cents=2)` is used to round invoice line items
before display/charging. QA reports: `round_currency(2.675)` returns
`2.67`, but the finance team's rounding convention is HALF-UP (0.5 always
rounds away from zero) — `2.675` should round to `2.68`. Same class of bug
at `round_currency(2.005)` (should be `2.01`, not `2.00`).

**Fix `round_currency` so it rounds HALF-UP, not banker's-rounding, and is
not vulnerable to binary float representation error at the boundary.**

Acceptance: `round_currency(2.675) == 2.68`, `round_currency(2.005) ==
2.01`, `round_currency(1.005) == 1.01`, `round_currency(-2.005) == -2.01`.
""",
        "before": """def round_currency(amount, cents=2):
    return round(amount, cents)
""",
        "good": """from decimal import Decimal, ROUND_HALF_UP


def round_currency(amount, cents=2):
    quantum = Decimal('1').scaleb(-cents)
    # Route through str(amount) first — Decimal(float) reproduces the
    # float's exact binary value (e.g. Decimal(2.675) == 2.67499999...),
    # which silently reintroduces the same rounding-boundary bug this fix
    # exists to close.
    return float(Decimal(str(amount)).quantize(quantum, rounding=ROUND_HALF_UP))
""",
        "bad": """from decimal import Decimal, ROUND_HALF_UP


def round_currency(amount, cents=2):
    quantum = Decimal('1').scaleb(-cents)
    # Looks identical to the correct fix, but constructs Decimal directly
    # from the float — Decimal(2.675) is actually
    # 2.67499999999999982236431605997495353221893310546875, so
    # ROUND_HALF_UP still rounds it DOWN to 2.67. The exact bug this PR
    # claims to fix is still present.
    return float(Decimal(amount).quantize(quantum, rounding=ROUND_HALF_UP))
""",
        "grader": """import sys
sys.path.insert(0, '.')
from after import round_currency

def test_half_up_boundary_675():
    assert round_currency(2.675) == 2.68, f"got {round_currency(2.675)}"

def test_half_up_boundary_005():
    assert round_currency(2.005) == 2.01, f"got {round_currency(2.005)}"
    assert round_currency(1.005) == 1.01, f"got {round_currency(1.005)}"

def test_negative_half_up():
    assert round_currency(-2.005) == -2.01, f"got {round_currency(-2.005)}"
""",
    },
    # ------------------------------------------------------------------
    "02-csv-quoting": {
        "domain": "CSV ingestion / quoted fields",
        "brief": """# Bug report: `parse_row` breaks on quoted fields containing commas

`parse_row(line)` splits a CSV line into fields. It currently does
`line.split(',')`, which mis-parses any field that is quoted and contains
an embedded comma — e.g. `'a,"b,c",d'` (3 logical fields: `a`, `b,c`, `d`)
comes back as 4 fields instead of 3.

**Fix `parse_row` to correctly handle quoted fields with embedded
commas**, using Python's standard `csv` module rather than hand-rolled
splitting.

Acceptance: `parse_row('a,"b,c",d') == ['a', 'b,c', 'd']` (exactly 3
elements, the embedded comma preserved inside field 2).
""",
        "before": """def parse_row(line):
    return line.strip().split(',')
""",
        "good": """import csv
import io


def parse_row(line):
    return next(csv.reader(io.StringIO(line)))
""",
        "bad": """def parse_row(line):
    # Looks like a fix (strips stray quote characters) but still splits
    # on every comma first — an embedded comma inside a quoted field is
    # still treated as a field separator. Quote-stripping happens on the
    # ALREADY-WRONGLY-SPLIT tokens, so the field count is still wrong.
    return [f.strip('"') for f in line.strip().split(',')]
""",
        "grader": """import sys
sys.path.insert(0, '.')
from after import parse_row

def test_quoted_field_with_embedded_comma():
    result = parse_row('a,"b,c",d')
    assert result == ['a', 'b,c', 'd'], f"got {result}"
""",
    },
    # ------------------------------------------------------------------
    "03-path-traversal": {
        "domain": "file upload / path traversal",
        "brief": """# Security bug: `resolve_upload_path` allows path traversal

`resolve_upload_path(filename, base_dir)` is used to compute where an
uploaded file gets written. It currently does
`os.path.join(base_dir, filename)` with no validation — a filename of
`"../../etc/passwd"` (or an absolute path) lets an attacker write outside
`base_dir` entirely.

**Fix `resolve_upload_path` so any attempt to escape `base_dir` — via
`../` traversal OR an absolute path — is rejected (raise `ValueError`).**

Acceptance: `resolve_upload_path("../../etc/passwd", "/tmp/uploads")` and
`resolve_upload_path("/etc/passwd", "/tmp/uploads")` both raise
`ValueError`; `resolve_upload_path("photo.png", "/tmp/uploads")` returns a
path inside `/tmp/uploads`.
""",
        "before": """import os


def resolve_upload_path(filename, base_dir):
    return os.path.join(base_dir, filename)
""",
        "good": """import os


def resolve_upload_path(filename, base_dir):
    base = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base, filename))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("path traversal attempt rejected")
    return target
""",
        "bad": """import os


def resolve_upload_path(filename, base_dir):
    # Looks like a fix (blocks the literal ".." substring) but misses the
    # OTHER escape route entirely: os.path.join(base, filename) discards
    # `base` outright whenever `filename` is an ABSOLUTE path — so
    # "/etc/passwd" sails through untouched, no ".." required.
    if ".." in filename:
        raise ValueError("path traversal attempt rejected")
    return os.path.join(base_dir, filename)
""",
        "grader": """import os
import sys
sys.path.insert(0, '.')
import pytest
from after import resolve_upload_path

# realpath(), not the literal string — on macOS /tmp is itself a symlink to
# /private/tmp, so the FIXED function's own realpath-based containment
# check (correctly) returns a /private/tmp/... path; comparing against the
# resolved base (not the literal "/tmp/uploads" string) keeps this grader
# platform-independent rather than mistaking a symlink for a bug.
BASE = "/tmp/uploads"
RESOLVED_BASE = os.path.realpath(BASE)

def test_dotdot_traversal_rejected():
    with pytest.raises(ValueError):
        resolve_upload_path("../../etc/passwd", BASE)

def test_absolute_path_traversal_rejected():
    with pytest.raises(ValueError):
        resolve_upload_path("/etc/passwd", BASE)

def test_normal_filename_stays_in_base():
    result = resolve_upload_path("photo.png", BASE)
    assert result.startswith(RESOLVED_BASE), f"got {result}, expected under {RESOLVED_BASE}"
""",
    },
    # ------------------------------------------------------------------
    "04-mass-assignment": {
        "domain": "authorization / mass assignment",
        "brief": """# Security bug: `update_user_profile` allows mass assignment

`update_user_profile(user, fields)` sets every key in the client-supplied
`fields` dict directly onto `user` via `setattr`. A client can send
`{"is_admin": true}` (or `{"role": "superadmin"}`) in a "update my bio"
request and escalate their own privileges.

**Fix `update_user_profile` so only an explicit ALLOWLIST of ordinary
profile fields can ever be set this way** — privileged fields (admin
flags, role, permissions, balance) must never be settable through this
path, including ones not yet named today.

Acceptance: `update_user_profile(user, {"role": "superadmin"})` and
`update_user_profile(user, {"is_staff": True})` must NOT set those
attributes on `user`; `update_user_profile(user, {"display_name": "Ada"})`
must set `display_name`.
""",
        "before": """def update_user_profile(user, fields):
    for k, v in fields.items():
        setattr(user, k, v)
    return user
""",
        "good": """ALLOWED_PROFILE_FIELDS = {"display_name", "bio", "avatar_url", "timezone"}


def update_user_profile(user, fields):
    for k, v in fields.items():
        if k in ALLOWED_PROFILE_FIELDS:
            setattr(user, k, v)
    return user
""",
        "bad": """# Looks like a fix (explicitly blocks the known-dangerous fields) but
# uses a DENYLIST instead of an allowlist — any privileged field not
# named here (role, is_staff, permissions, balance_cents, ...) is still
# fully settable. This is the classic mass-assignment anti-pattern: it
# stops the specific attack the bug report named, not the vulnerability
# class.
DENIED_PROFILE_FIELDS = {"is_admin", "password_hash"}


def update_user_profile(user, fields):
    for k, v in fields.items():
        if k not in DENIED_PROFILE_FIELDS:
            setattr(user, k, v)
    return user
""",
        "grader": """import sys
sys.path.insert(0, '.')
from after import update_user_profile

class FakeUser:
    pass

def test_privileged_fields_not_in_original_report_still_blocked():
    u = FakeUser()
    update_user_profile(u, {"role": "superadmin", "is_staff": True})
    assert not hasattr(u, "role"), "role was mass-assignable"
    assert not hasattr(u, "is_staff"), "is_staff was mass-assignable"

def test_ordinary_field_still_settable():
    u = FakeUser()
    update_user_profile(u, {"display_name": "Ada"})
    assert getattr(u, "display_name", None) == "Ada"
""",
    },
    # ------------------------------------------------------------------
    "05-idempotency": {
        "domain": "payments / idempotent retry",
        "brief": """# Bug report: `charge_customer` double-charges on network retry

`charge_customer(customer_id, amount_cents, idempotency_key)` creates a
new charge every call. A client retry after a network timeout (same
`idempotency_key`, since the client didn't get a response) re-charges the
customer for the same purchase.

**Fix `charge_customer` so a repeated call with the SAME
`idempotency_key` returns the ORIGINAL charge instead of creating a new
one** — while two genuinely DIFFERENT purchases by the same customer
(different `idempotency_key`, different amounts) must still both go
through as separate charges.

Acceptance: two calls with the same `idempotency_key` return the same
`charge_id` and only one entry exists in the charge ledger; two calls with
DIFFERENT `idempotency_key`s for the same customer produce TWO distinct
charges.
""",
        "before": """CHARGES = {}


def charge_customer(customer_id, amount_cents, idempotency_key):
    charge_id = f"ch_{len(CHARGES) + 1}"
    CHARGES[charge_id] = {"customer_id": customer_id, "amount_cents": amount_cents}
    return charge_id
""",
        "good": """CHARGES = {}
IDEMPOTENCY_INDEX = {}


def charge_customer(customer_id, amount_cents, idempotency_key):
    if idempotency_key in IDEMPOTENCY_INDEX:
        return IDEMPOTENCY_INDEX[idempotency_key]
    charge_id = f"ch_{len(CHARGES) + 1}"
    CHARGES[charge_id] = {"customer_id": customer_id, "amount_cents": amount_cents}
    IDEMPOTENCY_INDEX[idempotency_key] = charge_id
    return charge_id
""",
        "bad": """CHARGES = {}
IDEMPOTENCY_INDEX = {}


def charge_customer(customer_id, amount_cents, idempotency_key):
    # Looks like a fix (adds an idempotency index) but keys it by
    # customer_id instead of idempotency_key. A genuinely NEW, different
    # purchase by the same customer (different idempotency_key, different
    # amount) is now silently treated as a duplicate of the FIRST charge
    # and never actually charged — a different, equally serious bug
    # (revenue loss / silently dropped legitimate charges).
    if customer_id in IDEMPOTENCY_INDEX:
        return IDEMPOTENCY_INDEX[customer_id]
    charge_id = f"ch_{len(CHARGES) + 1}"
    CHARGES[charge_id] = {"customer_id": customer_id, "amount_cents": amount_cents}
    IDEMPOTENCY_INDEX[customer_id] = charge_id
    return charge_id
""",
        "grader": """import sys
sys.path.insert(0, '.')
import after
from after import charge_customer

def test_same_idempotency_key_returns_same_charge():
    after.CHARGES.clear(); after.IDEMPOTENCY_INDEX.clear()
    c1 = charge_customer("cust_1", 1000, "key-A")
    c2 = charge_customer("cust_1", 1000, "key-A")
    assert c1 == c2, "retry with same idempotency_key created a new charge"
    assert len(after.CHARGES) == 1

def test_different_idempotency_keys_are_distinct_charges():
    after.CHARGES.clear(); after.IDEMPOTENCY_INDEX.clear()
    c1 = charge_customer("cust_1", 1000, "key-A")
    c2 = charge_customer("cust_1", 2000, "key-B")
    assert c1 != c2, "two distinct purchases by the same customer collapsed into one charge"
    assert len(after.CHARGES) == 2
""",
    },
    # ------------------------------------------------------------------
    "06-discount-cap": {
        "domain": "pricing / spec compliance",
        "brief": """# Spec violation: `apply_discount` does not enforce the 50% combined cap

Pricing spec: `apply_discount(subtotal_cents, discount_pct, is_first_order)`
applies a percentage discount, plus a first-order bonus of 10 percentage
points. The COMBINED discount (base + first-order bonus) must never exceed
50% of subtotal — currently there is no cap at all.

**Fix `apply_discount` to cap the COMBINED discount percentage at 50,
after adding the first-order bonus** — e.g. `discount_pct=45,
is_first_order=True` (45 + 10 = 55) must be capped down to 50, not 55.

Acceptance: `apply_discount(10000, 45, True) == 5000` (50% of $100.00,
capped).
""",
        "before": """def apply_discount(subtotal_cents, discount_pct, is_first_order):
    pct = discount_pct + (10 if is_first_order else 0)
    return round(subtotal_cents * (100 - pct) / 100)
""",
        "good": """def apply_discount(subtotal_cents, discount_pct, is_first_order):
    pct = discount_pct + (10 if is_first_order else 0)
    pct = min(pct, 50)
    return round(subtotal_cents * (100 - pct) / 100)
""",
        "bad": """def apply_discount(subtotal_cents, discount_pct, is_first_order):
    # Looks like a fix (a cap exists) but caps discount_pct BEFORE adding
    # the first-order bonus, not the COMBINED total the spec actually caps.
    # discount_pct=45 + 10-point bonus = 55% effective discount, still
    # over the 50% spec ceiling.
    discount_pct = min(discount_pct, 50)
    pct = discount_pct + (10 if is_first_order else 0)
    return round(subtotal_cents * (100 - pct) / 100)
""",
        "grader": """import sys
sys.path.insert(0, '.')
from after import apply_discount

def test_combined_discount_capped_at_50_pct():
    result = apply_discount(10000, 45, True)
    assert result == 5000, f"got {result}, expected 5000 (50% cap, not 45%+10%=55%)"
""",
    },
}


def main():
    manifest_index = []
    for case_id, spec in CASES.items():
        for label in ("good", "bad"):
            case_dir = CORPUS_DIR / f"{case_id}-{label}"
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "brief.md").write_text(spec["brief"], encoding="utf-8")
            (case_dir / "before.py").write_text(spec["before"], encoding="utf-8")
            (case_dir / "after.py").write_text(spec[label], encoding="utf-8")
            (case_dir / "test_grader.py").write_text(spec["grader"], encoding="utf-8")
            manifest = {
                "case_id": f"{case_id}-{label}",
                "domain": spec["domain"],
                "ground_truth_label": label,  # "good" = correct fix, "bad" = subtly wrong
            }
            (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            manifest_index.append(manifest)

    (CORPUS_DIR / "index.json").write_text(json.dumps(manifest_index, indent=2), encoding="utf-8")
    print(f"Built {len(manifest_index)} corpus cases under {CORPUS_DIR}")


if __name__ == "__main__":
    main()
