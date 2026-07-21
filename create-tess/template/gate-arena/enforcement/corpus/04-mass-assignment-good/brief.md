# Security bug: `update_user_profile` allows mass assignment

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
