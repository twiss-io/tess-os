"""Synthetic stdlib preview tests. No signing fixtures or user listeners."""
import importlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "scripts" / "preview"
sys.path.insert(0, str(PREVIEW))
content = importlib.import_module("content")
lifecycle = importlib.import_module("lifecycle")
server = importlib.import_module("server")
cli = importlib.import_module("tesspreview")


@pytest.fixture
def site(tmp_path):
    public = tmp_path.resolve() / "public"
    public.mkdir()
    (public / "assets").mkdir()
    (public / "index.html").write_text('<base href="/dev/demo/"><script src="assets/app.js"></script>PUBLIC')
    (public / "assets" / "app.js").write_text('console.log("PUBLIC")')
    (public / "unselected.html").write_text("UNSELECTED")
    (tmp_path / "secret.html").write_text("PRIVATE-NEVER-SERVE")
    return public


@pytest.fixture
def launches(tmp_path, site):
    records = []
    def launch(slug="demo", **changes):
        config = {"slug": slug, "state_dir": str(tmp_path.resolve() / "state"),
                  "public_dir": str(site), "files": ["index.html", "assets/app.js"],
                  "port": 0, "localhost_only": True, "spa": False}
        config.update(changes)
        record = lifecycle.start(config, str(PREVIEW / "tesspreview.py"))
        records.append(record)
        return record
    yield launch
    for record in records:
        try:
            lifecycle.stop(record)
        except content.PreviewError:
            pass


def request(record, suffix, host="127.0.0.1"):
    return lifecycle.fetch(host, record["port"], "/dev/" + record["slug"] + suffix)


def test_lifecycle_assets_redirects_isolation_and_commands(launches):
    first = launches()
    second = launches("second")
    assert first["pid"] != os.getpid() and first["port"] != second["port"]
    assert request(first, "")[:2] == (308, "/dev/demo/")
    assert request(first, "/")[0] == request(first, "/assets/app.js?cache=1")[0] == 200
    assert request(first, "/unselected.html")[0] == 404
    assert lifecycle.fetch("127.0.0.1", first["port"], "/dev/second/")[0] == 404
    assert lifecycle.verify(first) == ["127.0.0.1"]
    result = cli.handoff(first)
    assert result["lan_url"] is None and "token" not in json.dumps(result)
    assert result["localhost_url"].endswith("/dev/demo")
    assert "restart" in result["commands"] and "stop" in result["commands"]


@pytest.mark.parametrize("path", [
    "/../secret.html", "/%2e%2e/secret.html", "/%252e%252e/secret.html",
    "/assets%2fapp.js", "/assets/%5csecret.html", "/assets/..%2fsecret.html",
    "/.git/config", "/.env", "/.tess/state", "/kb/private.html", "/brain/index.html",
    "/credentials/key.json", "/private/index.html", "/AGENTS.md", "/%00index.html",
    "/assets/", "/unselected.html", "/docs/internal.html", "/status", "/stop",
])
def test_reverse_paths_do_not_disclose_files(launches, path):
    record = launches(spa=True)
    code, _, body = request(record, path)
    if path in ("/assets/", "/status", "/stop"):
        # Extensionless SPA routes are the approved index, never directory listings/control.
        assert code == 200 and body.startswith(b'<base href="/dev/demo/">')
    else:
        assert code == 404
    assert b"PRIVATE-NEVER-SERVE" not in body and b"unselected.html" not in body


def test_spa_deep_refresh_base_and_missing_assets(launches):
    record = launches(spa=True)
    index = request(record, "/")[2]
    assert request(record, "/one/two/")[2] == index
    assert b'<base href="/dev/demo/">' in index
    assert request(record, "/assets/app.js")[0] == 200
    assert request(record, "/one/missing.js")[0] == 404
    assert lifecycle.verify(record) == ["127.0.0.1"]


def test_snapshot_immutable_after_root_and_asset_replacement(launches, site):
    record = launches()
    original = request(record, "/")[2]
    site.rename(site.with_name("old-public"))
    site.symlink_to(site.parent)
    assert request(record, "/")[2] == original
    assert request(record, "/secret.html")[0] == 404


def test_occupied_port_falls_back_without_disturbing_listener(launches):
    with socket.socket() as occupied:
        occupied.bind(("0.0.0.0", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        record = launches(port=port)
        assert record["port"] != port
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass
        assert occupied.fileno() >= 0


def test_duplicate_slug_refused_without_stopping_first(launches):
    record = launches()
    with pytest.raises(content.PreviewError, match="startup refused"):
        launches()
    assert request(record, "/")[0] == 200


def test_control_requires_token_and_is_never_public(launches):
    record = launches()
    assert lifecycle.fetch("127.0.0.1", record["control_port"], "/status")[0] == 404
    bad = dict(record, token="wrong")
    with pytest.raises(content.PreviewError, match="authenticated"):
        lifecycle.stop(bad)
    assert request(record, "/")[0] == 200


def test_reused_pid_is_never_signaled(launches, monkeypatch):
    record = launches()
    with socket.socket() as unrelated:
        unrelated.bind(("127.0.0.1", 0))
        unrelated.listen()
        unrelated.settimeout(2)
        def reply():
            connection, _ = unrelated.accept()
            with connection:
                connection.recv(4096)
                connection.sendall(b"HTTP/1.0 404 Nope\r\nContent-Length: 0\r\n\r\n")
        thread = threading.Thread(target=reply)
        thread.start()
        stale = dict(record, pid=os.getpid(), control_port=unrelated.getsockname()[1])
        monkeypatch.setattr(os, "kill", lambda *args: pytest.fail("Launcher must never signal a PID"))
        with pytest.raises(content.PreviewError):
            lifecycle.stop(stale)
        thread.join()
        assert unrelated.fileno() >= 0 and request(record, "/")[0] == 200


def test_stop_restart_and_crash_recovery(launches, site):
    record = launches()
    lifecycle.stop(record)
    with pytest.raises(content.PreviewError):
        lifecycle.control(record)
    (site / "index.html").write_text("FRESH")
    replacement = launches()
    assert request(replacement, "/")[2] == b"FRESH"
    # This is our synthetic spawned child only, to exercise a real crash.
    os.kill(replacement["pid"], signal.SIGKILL)
    for _ in range(50):
        try:
            lifecycle.control(replacement)
        except content.PreviewError:
            break
        __import__("time").sleep(0.02)
    restarted = launches()
    assert restarted["instance"] != replacement["instance"]
    assert request(restarted, "/")[2] == b"FRESH"


@pytest.mark.parametrize("selection", [[], ["assets/app.js"], ["index.html", "index.html"],
    ["index.html", "../secret.html"], ["index.html", ".env"],
    ["index.html", "kb/private.html"], ["index.html", "credentials.json"],
    ["index.html", "secret.key"], ["index.html", "AGENTS.md"]])
def test_explicit_selection_fail_closed(site, selection):
    with pytest.raises((content.PreviewError, OSError)):
        content.snapshot(str(site), selection)


def test_symlinks_hardlinks_and_broad_roots_rejected(site):
    (site / "escape.html").symlink_to(site.parent / "secret.html")
    with pytest.raises(OSError):
        content.snapshot(str(site), ["index.html", "escape.html"])
    (site / "alias").symlink_to(site.parent)
    with pytest.raises(OSError):
        content.snapshot(str(site), ["index.html", "alias/outside.html"])
    os.link(site.parent / "secret.html", site / "hard.html")
    with pytest.raises(content.PreviewError, match="hardlinked"):
        content.snapshot(str(site), ["index.html", "hard.html"])
    (site / ".git").mkdir()
    with pytest.raises(content.PreviewError, match="workspace"):
        content.snapshot(str(site), ["index.html"])


def test_snapshot_resource_bounds(site, monkeypatch):
    monkeypatch.setattr(content, "MAX_FILE_BYTES", 2)
    with pytest.raises(content.PreviewError, match="16 MiB"):
        content.snapshot(str(site), ["index.html"])
    monkeypatch.setattr(content, "MAX_FILE_BYTES", 1024)
    monkeypatch.setattr(content, "MAX_TOTAL_BYTES", 2)
    with pytest.raises(content.PreviewError, match="64 MiB"):
        content.snapshot(str(site), ["index.html"])
    monkeypatch.setattr(content, "MAX_FILES", 1)
    with pytest.raises(content.PreviewError, match="512"):
        content.snapshot(str(site), ["index.html", "assets/app.js"])


def test_concurrent_nested_symlink_swap_cannot_escape(site, monkeypatch):
    original_open = os.open
    switched = False
    def swapping_open(path, flags, *args, **kwargs):
        nonlocal switched
        if path == "app.js" and not switched:
            switched = True
            (site / "assets" / "app.js").unlink()
            (site / "assets" / "app.js").symlink_to(site.parent / "secret.html")
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, "open", swapping_open)
    with pytest.raises(OSError):
        content.snapshot(str(site), ["index.html", "assets/app.js"])
    assert switched


def test_concurrent_root_swap_stays_on_pinned_public_directory(site, monkeypatch):
    original_read = content.read_public
    switched = False
    def swapping_read(fd, name):
        nonlocal switched
        if not switched:
            switched = True
            site.rename(site.with_name("old-public"))
            site.symlink_to(site.parent)
        return original_read(fd, name)
    monkeypatch.setattr(content, "read_public", swapping_read)
    selected = content.snapshot(str(site), ["index.html", "assets/app.js"])
    assert b"PUBLIC" in selected["index.html"][0]
    assert all(b"PRIVATE-NEVER-SERVE" not in data[0] for data in selected.values())


def test_concurrent_file_edit_fails_closed(site, monkeypatch):
    original_read = os.read
    switched = False
    def editing_read(fd, size):
        nonlocal switched
        data = original_read(fd, size)
        if data and not switched:
            switched = True
            (site / "index.html").write_text("CHANGED-DURING-SNAPSHOT")
        return data
    monkeypatch.setattr(os, "read", editing_read)
    with pytest.raises(content.PreviewError, match="changed during snapshot"):
        content.snapshot(str(site), ["index.html"])


def test_nonregular_and_credential_files_rejected(site):
    os.mkfifo(site / "fifo.html")
    with pytest.raises(content.PreviewError, match="regular"):
        content.snapshot(str(site), ["index.html", "fifo.html"])
    (site / "credentials.json").write_text("PRIVATE-NEVER-SERVE")
    with pytest.raises(content.PreviewError, match="private"):
        content.snapshot(str(site), ["index.html", "credentials.json"])


def test_private_state_permissions_and_symlink_guard(tmp_path):
    root = tmp_path.resolve() / "state"
    root.mkdir(mode=0o755)
    with pytest.raises(content.PreviewError, match="0700"):
        with content.directory(str(root), private=True):
            pass
    root.chmod(0o700)
    (root / "demo.log").symlink_to(tmp_path / "unrelated.log")
    with content.directory(str(root), private=True) as fd:
        with pytest.raises(OSError):
            lifecycle.private_file(fd, "demo.log", os.O_CREAT | os.O_WRONLY)
    assert not (tmp_path / "unrelated.log").exists()


def test_lan_detection_platform_paths_and_no_lan(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: "inet 127.0.0.1\n inet 192.168.42.8\n")
    assert server.lan_ip() == "192.168.42.8"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: json.dumps([
        {"addr_info": [{"family": "inet", "scope": "global", "local": "172.22.12.3"}]}]))
    assert server.lan_ip() == "172.22.12.3"  # WSL/Linux same interface API
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: "[]")
    assert server.lan_ip() is None


def test_lan_bind_and_host_address_verification(launches):
    record = launches(localhost_only=False)
    assert record["host"] == "0.0.0.0"
    checked = lifecycle.verify(record)
    assert checked[0] == "127.0.0.1"
    if server.lan_ip():
        assert checked[1] == server.lan_ip()
        assert cli.handoff(record)["lan_url"] is not None


def test_cli_status_restart_logs_and_missing_state(launches):
    record = launches()
    base = [sys.executable, str(PREVIEW / "tesspreview.py"),
            "--state-dir", record["config"]["state_dir"], "--json"]
    for command in ("status", "verify", "logs"):
        result = subprocess.run(base + [command, "demo"], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert record["token"] not in result.stdout + result.stderr
    result = subprocess.run(base + ["restart", "demo"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    fresh = lifecycle.read_record(record["config"]["state_dir"], "demo")
    try:
        assert fresh["instance"] != record["instance"]
        assert lifecycle.verify(fresh)
    finally:
        lifecycle.stop(fresh)
    result = subprocess.run(base + ["status", "missing"], capture_output=True, text=True)
    assert result.returncode == 1


def test_current_ip_not_hardcoded_and_no_lan_limitation(launches, monkeypatch):
    record = launches(localhost_only=False)
    monkeypatch.setattr(cli, "lan_ip", lambda: None)
    assert cli.handoff(record)["lan_url"] is None
    monkeypatch.setattr(lifecycle, "lan_ip", lambda: None)
    assert lifecycle.verify(record) == ["127.0.0.1"]
