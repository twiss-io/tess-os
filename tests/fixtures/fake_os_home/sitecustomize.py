"""Test-only: give a tessctl subprocess a fake home in the OS user record.

tessctl finds the operator key under pwd.getpwuid(os.getuid()).pw_dir and
ignores $HOME / $XDG_CONFIG_HOME (v1.0.0 security review round 3, N-2), so a
test cannot move the key with an environment variable. Tests that run tessctl
as a subprocess put this directory on PYTHONPATH and name the fake home in
TESS_TEST_OS_HOME; Python imports this module at start-up and replaces
pwd.getpwuid for that process only. Production code has no such switch: this
file is never on the path outside the test suite.
"""
import os

if os.environ.get("TESS_TEST_OS_HOME"):
    try:
        import pwd
    except ImportError:  # no user database: nothing to replace
        pwd = None
    if pwd is not None:
        _real_getpwuid = pwd.getpwuid

        def _fake_getpwuid(uid):
            rec = _real_getpwuid(uid)
            home = os.environ.get("TESS_TEST_OS_HOME") or rec.pw_dir
            return pwd.struct_passwd((rec.pw_name, rec.pw_passwd, rec.pw_uid, rec.pw_gid,
                                      rec.pw_gecos, home, rec.pw_shell))

        pwd.getpwuid = _fake_getpwuid
