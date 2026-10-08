"""Focused independent-review regression cases; synthetic owned listeners only."""
import socket
import sys
import threading
import time

import pytest

from test_lan_preview import cli, content, launches, lifecycle, request, server, site


@pytest.mark.parametrize("html", [
    '<script src="assets/app.js"></script>',
    '<base href="/"><script src="assets/app.js"></script>',
    '<base href="/dev/wrong/"><script src="assets/app.js"></script>',
    '<base href="/dev/demo/"><script src="/assets/app.js"></script>',
    '<script src="assets/app.js"></script><base href="/dev/demo/">',
    '<base href="/dev/demo/"><script src="assets/missing.js"></script>',
])
def test_readiness_rejects_actual_broken_html_asset_resolution(site, launches, html):
    (site / "index.html").write_text(html)
    before = (site / "index.html").read_bytes()
    record = launches(spa=True)
    with pytest.raises(content.PreviewError, match="HTML asset"):
        lifecycle.verify(record)
    assert (site / "index.html").read_bytes() == before  # no silent source adaptation


@pytest.mark.parametrize("html,spa", [
    ('<script src="assets/app.js"></script>', False),
    ('<base href="/dev/demo/"><script src="assets/app.js?build=1"></script>', True),
    ('<script src="/dev/demo/assets/app.js"></script>', True),
    ('<base href="/dev/demo/"><link rel="stylesheet" href="assets/nested/site.css">', True),
])
def test_readiness_accepts_correct_relative_absolute_and_nested_assets(site, launches, html, spa):
    (site / "assets" / "nested").mkdir()
    (site / "assets" / "nested" / "site.css").write_text("body { color: black }")
    (site / "index.html").write_text(html)
    record = launches(spa=spa, files=["index.html", "assets/app.js", "assets/nested/site.css"])
    assert lifecycle.verify(record) == ["127.0.0.1"]


def test_selected_nested_html_resolves_against_its_own_directory(site, launches):
    (site / "pages").mkdir()
    (site / "pages" / "nested.html").write_text('<script src="../assets/app.js"></script>')
    record = launches(files=["index.html", "assets/app.js", "pages/nested.html"])
    assert lifecycle.verify(record) == ["127.0.0.1"]


def test_duplicate_deep_assets_do_not_hide_a_route_dependent_spa_base(site, launches):
    nested = site / "preview-readiness" / "one" / "two" / "assets"
    nested.mkdir(parents=True)
    (nested / "app.js").write_text('console.log("PUBLIC")')
    (site / "index.html").write_text('<script src="assets/app.js"></script>')
    record = launches(spa=True, files=["index.html", "assets/app.js",
                                      "preview-readiness/one/two/assets/app.js"])
    with pytest.raises(content.PreviewError, match="depend on the deep route"):
        lifecycle.verify(record)


@pytest.mark.parametrize("slug", ["other-project", "preview-isolation-probe"])
def test_legal_slug_and_selected_negative_probe_names_do_not_collide(site, launches, slug):
    (site / "index.html").write_text('<base href="/dev/' + slug + '/"><script src="unknown.js"></script>')
    (site / "unknown.js").write_text("PUBLIC")
    (site / "preview-denial-probe-0.js").write_text("PUBLIC")
    record = launches(slug, spa=True,
                      files=["index.html", "unknown.js", "preview-denial-probe-0.js"])
    assert lifecycle.verify(record) == ["127.0.0.1"]
    assert request(record, "/.git/config")[0] == 404
    assert request(record, "/.env")[0] == 404


def test_absolute_header_deadline_recovers_all_trickle_slots_and_control(launches):
    record = launches()
    clients = [socket.create_connection(("127.0.0.1", record["port"]), timeout=2) for _ in range(16)]
    completed = threading.Event()
    active = list(clients)
    def trickle():
        while not completed.wait(0.2):
            for client in list(active):
                try:
                    client.sendall(b"G")
                except OSError:
                    active.remove(client)
    thread = threading.Thread(target=trickle)
    try:
        for client in clients:
            client.sendall(b"G")
        thread.start()
        # The lifecycle listener has its own capacity and remains available.
        assert lifecycle.control(record)
        time.sleep(server.HEADER_SECONDS + 0.8)
        assert request(record, "/")[0] == 200  # no manual client close first
        assert lifecycle.control(record)
        # Each original socket must be EOF or reset despite continued bytes.
        for client in clients:
            client.settimeout(0.5)
            try:
                assert client.recv(1) == b""
            except (ConnectionResetError, BrokenPipeError):
                pass
    finally:
        completed.set()
        if thread.is_alive():
            thread.join(timeout=2)
        for client in clients:
            client.close()


def test_response_write_uses_single_absolute_budget(monkeypatch):
    # Deterministic response-side stall proof: headers consume nearly all of
    # the wall-clock allowance; the body cannot get a fresh five seconds.
    handler = object.__new__(server.QuietHandler)
    class Connection:
        budgets = []
        def settimeout(self, value):
            self.budgets.append(value)
    class Writer:
        def write(self, value):
            raise TimeoutError("simulated stalled client")
    handler.connection, handler.wfile = Connection(), Writer()
    handler.send_response = lambda *args: None
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    times = iter([100.0, 104.9])
    monkeypatch.setattr(server.time, "monotonic", lambda: next(times))
    with pytest.raises(TimeoutError):
        handler.reply(200, b"PUBLIC")
    assert handler.connection.budgets[0] == server.RESPONSE_SECONDS
    assert 0 < handler.connection.budgets[1] < 0.2


@pytest.mark.parametrize("mode", ["nat", "none", "unknown", "wsl1", "bridged", "virtioproxy", "consomme"])
def test_wsl_unsupported_or_unknown_modes_never_advertise_guest_lan_ip(monkeypatch, mode):
    monkeypatch.setattr(server, "wsl_mode", lambda: mode)
    monkeypatch.setattr(server.subprocess, "check_output", lambda *args, **kwargs:
                        pytest.fail("Do not choose a NAT/unknown guest interface as LAN"))
    status = server.network_status()
    assert status["address"] is None and status["wsl_mode"] == mode
    assert "Only localhost" in status["limitation"]


def test_wsl_mirrored_candidate_is_explicitly_qualified(monkeypatch):
    monkeypatch.setattr(server, "wsl_mode", lambda: "mirrored")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(server.subprocess, "check_output", lambda *args, **kwargs:
        '[{"addr_info":[{"family":"inet","scope":"global","local":"192.168.23.9"}]}]')
    status = server.network_status()
    assert status["address"] == "192.168.23.9"
    assert "second-device reachability remain unverified" in status["limitation"]


def test_wsl_detection_uses_actual_mode_and_missing_utility_is_unknown(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(server.os, "uname", lambda: SimpleNamespace(release="6.6.87-microsoft-standard-WSL2"))
    calls = []
    def response(command, **kwargs):
        calls.append(command)
        return "NAT\n"
    monkeypatch.setattr(server.subprocess, "check_output", response)
    assert server.wsl_mode() == "nat"
    assert calls == [["/usr/bin/wslinfo", "--networking-mode"]]
    def missing(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(server.subprocess, "check_output", missing)
    assert server.wsl_mode() == "unknown"


def test_wsl_nat_handoff_and_verify_do_not_turn_guest_success_into_lan_evidence(launches, monkeypatch):
    record = launches(localhost_only=False)
    monkeypatch.setattr(server, "wsl_mode", lambda: "nat")
    checked = lifecycle.verify(record)
    assert checked == ["127.0.0.1"]
    result = cli.handoff(record, checked)
    assert result["lan_url"] is None
    assert "WSL networking mode nat" in result["lan_limitation"]
    assert result["second_device_tested"] is False
