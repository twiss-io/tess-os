# Security bug: `resolve_upload_path` allows path traversal

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
