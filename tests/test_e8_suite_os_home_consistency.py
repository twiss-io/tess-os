"""E8 (T1): one OS home per test process, whichever way it is asked.

tests/conftest.py fakes the OS user record's home twice: in this process (pwd.getpwuid patched,
TESS_TEST_OS_HOME first) and in every interpreter of the suite venv through a .pth file (which
the hooks' `python3 -I` still loads). Under pytest-xdist a worker inherited the controller's
TESS_TEST_OS_HOME but wrote its own home into its .pth, so the two disagreed and a hook judged a
different ~/.config/tess than the test named. CI runs this file with `-n 2` as well as serially.
"""
from __future__ import annotations

import os
import pwd
import subprocess
import tempfile

_PROBE = "import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)"


def _scrubbed_home(extra: dict | None = None) -> str:
    """The OS home a hook sees when started the way test_codex_gate._hook starts it."""
    env = {"HOME": "/nonexistent-e8", "PATH": os.environ["PATH"], **(extra or {})}
    return subprocess.run(["python3", "-I", "-B", "-c", _PROBE], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


def test_hook_interpreter_and_test_process_share_one_os_home():
    assert _scrubbed_home() == pwd.getpwuid(os.getuid()).pw_dir


def test_hook_interpreter_honours_the_variable_when_it_is_passed(tmp_path):
    assert _scrubbed_home({"TESS_TEST_OS_HOME": str(tmp_path)}) == str(tmp_path)


def test_suite_os_home_is_a_temp_folder_not_the_operator_home():
    tmp = os.path.realpath(tempfile.gettempdir())
    assert os.path.realpath(_scrubbed_home()).startswith(tmp + os.sep)
    assert os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir).startswith(tmp + os.sep)


def test_each_xdist_worker_has_its_own_home():
    """Under xdist, the worker's home is the one its own .pth names, not the controller's."""
    if not os.environ.get("PYTEST_XDIST_WORKER"):
        return
    assert os.environ["TESS_TEST_OS_HOME"] == _scrubbed_home()
