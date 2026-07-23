"""Reporter-format coverage for generated-app ``node --test`` assertions."""

from __future__ import annotations

import subprocess

import pytest

from _node_server import assert_node_test_passed


@pytest.mark.parametrize(
    "stdout",
    [
        "# tests 3\n# pass 3\n# fail 0\n",
        "ℹ tests 3\nℹ pass 3\nℹ fail 0\n",
    ],
    ids=["tap", "spec"],
)
def test_accepts_successful_node_test_reporters(stdout):
    result = subprocess.CompletedProcess(["node", "--test"], 0, stdout=stdout, stderr="")

    assert_node_test_passed(result, description="generated test suite")


def test_rejects_nonzero_exit_even_when_summary_claims_no_failures():
    result = subprocess.CompletedProcess(
        ["node", "--test"], 1, stdout="# pass 3\n# fail 0\n", stderr=""
    )

    with pytest.raises(AssertionError, match="exited with code 1"):
        assert_node_test_passed(result, description="generated test suite")


def test_rejects_failure_summary_even_if_exit_code_is_inconsistent():
    result = subprocess.CompletedProcess(
        ["node", "--test"], 0, stdout="ℹ pass 2\nℹ fail 1\n", stderr=""
    )

    with pytest.raises(AssertionError, match="reported 1 failed test"):
        assert_node_test_passed(result, description="generated test suite")
