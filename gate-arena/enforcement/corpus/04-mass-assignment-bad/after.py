# Looks like a fix (explicitly blocks the known-dangerous fields) but
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
