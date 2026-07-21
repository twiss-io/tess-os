import os
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
