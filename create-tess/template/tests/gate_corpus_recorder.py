"""
pytest plugin (v1.0.x round 4): record every shell command the test corpora
hand to the gate's decide(), with the decision, for the real-shell
conformance harness (tests/shell_conformance.py).

Off unless TESS_RECORD_GATE_CORPUS names an output file. Load it with
`-p gate_corpus_recorder`. It wraps decide() in each gate module as the module
is loaded, so it adds no work to tests that never load the gate.
"""

from __future__ import annotations

import functools
import importlib.machinery
import json
import os

_OUT = os.environ.get("TESS_RECORD_GATE_CORPUS")
_STATE = {"test": "<collect>", "depth": 0, "fh": None, "tmp": None, "idx": {}}
_REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), os.pardir))


def _wrap(mod) -> None:
    orig = getattr(mod, "decide", None)
    if orig is None or getattr(orig, "_tess_recorded", False):
        return

    @functools.wraps(orig)
    def decide(data, root, runtime, *a, **k):
        _STATE["depth"] += 1
        try:
            res = orig(data, root, runtime, *a, **k)
        finally:
            _STATE["depth"] -= 1
        if _STATE["depth"] == 0 and _STATE["fh"] is not None:
            _record(data, root, runtime, res)
        return res

    decide._tess_recorded = True
    mod.decide = decide


def _record(data, root, runtime, res) -> None:
    ti = data.get("tool_input") if isinstance(data, dict) else None
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str):
        return
    t = _STATE["test"]
    i = _STATE["idx"].get(t, 0)
    _STATE["idx"][t] = i + 1
    rec = {"t": t, "i": i, "cmd": cmd, "cwd": data.get("cwd"), "root": os.path.realpath(str(root)),
           "root_raw": str(root),
           "home": os.environ.get("HOME"), "tmp": _STATE["tmp"], "repo": _REPO, "rt": runtime,
           "mode": data.get("permission_mode"), "d": (res[0] if isinstance(res, tuple) else res) or "allow"}
    _STATE["fh"].write(json.dumps(rec) + "\n")


def _patch_loader() -> None:
    loader = importlib.machinery.SourceFileLoader
    orig = loader.exec_module
    if getattr(orig, "_tess_recorded", False):
        return

    def exec_module(self, module):
        orig(self, module)
        if str(getattr(module, "__file__", "") or "").endswith("tess-gate.py"):
            _wrap(module)

    exec_module._tess_recorded = True
    loader.exec_module = exec_module


def pytest_configure(config):
    if not _OUT:
        return
    _STATE["fh"] = open(_OUT, "a", encoding="utf-8")
    _patch_loader()


def pytest_sessionstart(session):
    if not _OUT:
        return
    try:
        _STATE["tmp"] = os.path.realpath(str(session.config._tmp_path_factory.getbasetemp()))
    except Exception:  # noqa: BLE001 - the temp root is only a path hint
        _STATE["tmp"] = None


def pytest_runtest_setup(item):
    _STATE["test"] = item.nodeid


def pytest_unconfigure(config):
    if _STATE["fh"] is not None:
        _STATE["fh"].close()
        _STATE["fh"] = None
