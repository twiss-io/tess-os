"""MANDATORY adversarial/repro test (b): a RESOLVED integration emits a
real client and the generated app boots + the client is wired to a real
route — proven by actually booting the generated app as a subprocess and
making real HTTP calls to it, over `node`'s real global `fetch()`.

**No real paid API calls are ever made.** Every test here points the
generated connector's `base_url_override_env` (a manifest-declared,
disclosed escape hatch — connectors/registry/*/README.md "Base URL
override") at a LOCAL mock HTTPS server this file starts itself
(`127.0.0.1`, ephemeral port, self-signed cert) — never `api.anthropic.com`
/ `api.openai.com` / `generativelanguage.googleapis.com`. The mock server
returns hand-authored, representative response bodies matching each
provider's real documented shape (same fixtures committed under
`connectors/registry/<id>/fixtures/`) — not live traffic.

**HTTPS, not plain HTTP (Cyra LOW F6, PR #84 security review fix-up
round):** the generated runtime now REFUSES a non-`https://`
`base_url_override_env` value (see `spec_engine.codegen._render_connector_runtime_js`'s
`resolveBaseUrl()`) — so the mock provider here must genuinely speak TLS
for the existing round-trip tests to keep proving a real, working
connector, not just a refused override. The self-signed cert (CN/SAN
`127.0.0.1`) is generated ONCE per test session via the system `openssl`
CLI (a standard OS tool this repo's own CI already assumes for secret
scanning, `.github/workflows/ci.yml` — not a new pip/npm project
dependency) and trusted by the generated app's Node process via the
standard `NODE_EXTRA_CA_CERTS` env var — never by disabling TLS
verification (`NODE_TLS_REJECT_UNAUTHORIZED` is never touched). The whole
module skips cleanly if `openssl` isn't on PATH, same pattern as the
existing no-`node` skip.

Mirrors `test_codegen_app_boots.py`'s subprocess-boot conventions exactly
(same `node_server` fixture shape, same throwaway-tmp_path discipline, same
clean skip when no `node` binary is on PATH).
"""

from __future__ import annotations

import json
import re
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from shutil import which

import pytest

import _spec_engine_paths  # noqa: F401 -- sys.path bootstrap

from spec_engine.connector_resolver import resolve_connectors
from spec_engine.content import DataModel, HowItLooks, HowItWorks, WhatItDoes, new_id, utc_now_iso
from spec_engine.codegen import generate_app
from spec_engine.gate_approval import sign_local_approval
from spec_engine.spec_builder import build_spec
from spec_engine.types import Plan

HAS_NODE = which("node") is not None
HAS_OPENSSL = which("openssl") is not None
pytestmark = [
    pytest.mark.skipif(not HAS_NODE, reason="node binary not found on PATH"),
    pytest.mark.skipif(not HAS_OPENSSL, reason="openssl binary not found on PATH (needed for the HTTPS mock provider)"),
]

BOOT_TIMEOUT_SECONDS = 10
_LISTEN_RE = re.compile(r"listening on http://localhost:(\d+)")


def _spec_with_integrations(integration_names):
    plan = Plan(
        plan_id=new_id("plan"),
        mission_id=None,
        created_at=utc_now_iso(),
        source_type="structured_brief",
        input_excerpt="An AI-powered app",
        what_it_does=WhatItDoes(summary="Calls a model provider."),
        how_it_looks=HowItLooks(),
        how_it_works=HowItWorks(integrations=list(integration_names)),
        data_model=DataModel(),
        summary_for_approval="summary",
        resolved_connectors=resolve_connectors(integration_names),
    )
    approval = sign_local_approval(plan, approved_by="Xavier")
    return build_spec(plan, approval)


@pytest.fixture(scope="session")
def _self_signed_cert(tmp_path_factory):
    """A throwaway self-signed cert (CN/SAN `127.0.0.1`), generated ONCE
    per test session via the system `openssl` CLI — see module docstring.
    Returns `(cert_path, key_path)`. Every `mock_provider`/`_start_mock`
    HTTPS server in this file loads this same cert; every `node_server`
    process trusts it via `NODE_EXTRA_CA_CERTS` (never a global TLS-
    verification bypass)."""
    cert_dir = tmp_path_factory.mktemp("connectors-https-mock-cert")
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"
    san_config = cert_dir / "san.cnf"
    san_config.write_text(
        "[req]\n"
        "distinguished_name = req_distinguished_name\n"
        "x509_extensions = v3_req\n"
        "prompt = no\n"
        "[req_distinguished_name]\n"
        "CN = 127.0.0.1\n"
        "[v3_req]\n"
        "subjectAltName = @alt_names\n"
        "[alt_names]\n"
        "IP.1 = 127.0.0.1\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key_path), "-out", str(cert_path),
            "-days", "1", "-nodes", "-config", str(san_config),
        ],
        check=True,
        capture_output=True,
    )
    return cert_path, key_path


@pytest.fixture
def node_server(_self_signed_cert):
    """Same shape as test_codegen_app_boots.py's own `node_server` fixture
    (kept independent per that file's own module-collision-avoidance
    convention, not imported) — plus `NODE_EXTRA_CA_CERTS`, so the
    generated app's real Node `fetch()` trusts this file's self-signed
    HTTPS mock provider(s) without disabling TLS verification."""
    import os

    cert_path, _key_path = _self_signed_cert
    procs = []

    def start(target_dir, extra_env=None):
        env = {**os.environ, "PORT": "0", "NODE_EXTRA_CA_CERTS": str(cert_path)}
        if extra_env:
            env.update(extra_env)
        proc = subprocess.Popen(
            ["node", str(target_dir / "src" / "server.js")],
            cwd=str(target_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        procs.append(proc)
        deadline = time.monotonic() + BOOT_TIMEOUT_SECONDS
        port = None
        stdout_so_far = ""
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stderr_out = proc.stderr.read()
                raise AssertionError(
                    f"generated server exited early (code {proc.returncode}) before reporting "
                    f"'listening'. stdout={stdout_so_far!r} stderr={stderr_out!r}"
                )
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            stdout_so_far += line
            match = _LISTEN_RE.search(line)
            if match:
                port = int(match.group(1))
                break
        if port is None:
            proc.terminate()
            raise AssertionError(
                f"generated server did not report 'listening' within {BOOT_TIMEOUT_SECONDS}s. "
                f"stdout so far: {stdout_so_far!r}"
            )
        return proc, f"http://localhost:{port}"

    yield start

    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


@pytest.fixture
def mock_provider(_self_signed_cert):
    """A LOCAL, loopback-only HTTPS server (never a real provider) that
    records every request it receives and replies from a caller-set
    response queue. `set_response(status, body, headers=None)` queues
    exactly one response; requests beyond the queue re-serve the last
    queued response. `requests` is the recorded list of
    `{method, path, headers, body}` dicts, in receipt order — used to
    assert the generated client sent the RIGHT auth header / version pin /
    body shape, not just that SOME request happened. Genuinely speaks TLS
    (self-signed, `_self_signed_cert`) — see module docstring for why a
    plain-HTTP mock is no longer sufficient after the https-pin fix."""
    received = []
    responses = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _handle(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            with lock:
                received.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": json.loads(raw) if raw else None,
                    }
                )
                status, body, headers = responses[-1] if responses else (200, {}, {})
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)

        do_POST = _handle

        def log_message(self, *a):  # noqa: D401 -- silence default stderr logging
            pass

    cert_path, key_path = _self_signed_cert
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(str(cert_path), str(key_path))
    server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    class Mock:
        base_url = f"https://127.0.0.1:{port}"
        requests = received

        def set_response(self, status, body, headers=None):
            with lock:
                responses.append((status, body, headers or {}))

    yield Mock()
    server.shutdown()
    thread.join(timeout=5)


def _get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _post(url, payload, timeout=5):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# --------------------------------------------------------------------------
# MANDATORY (b) — resolved integration -> real client, wired to a real
# route, real HTTP round-trip against a MOCKED external provider.
# --------------------------------------------------------------------------


def test_anthropic_connector_boots_and_round_trips_over_real_http(tmp_path, node_server, mock_provider):
    mock_provider.set_response(
        200,
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello from the mock!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 11, "output_tokens": 4},
        },
    )
    spec = _spec_with_integrations(["Anthropic"])
    result = generate_app(spec, tmp_path)
    assert result.scaffold_plan.codegen_status == "generated"

    proc, base_url = node_server(
        tmp_path,
        extra_env={"ANTHROPIC_API_KEY": "test-only-not-a-real-key", "ANTHROPIC_API_BASE_URL": mock_provider.base_url},
    )
    status, body = _post(
        f"{base_url}/api/integrations/anthropic",
        {"model": "claude-sonnet-4-5", "messages": [{"role": "user", "text": "hi"}], "max_tokens": 50},
    )
    assert status == 200, body
    assert body["status"] == "ok"
    assert body["output"]["text"] == "Hello from the mock!"
    assert body["output"]["usage"] == {"input_tokens": 11, "output_tokens": 4}

    # The client sent the RIGHT auth surface — proves it is genuinely wired,
    # not a stub that happens to also return 200.
    assert len(mock_provider.requests) == 1
    sent = mock_provider.requests[0]
    assert sent["path"] == "/v1/messages"
    assert sent["headers"]["x-api-key"] == "test-only-not-a-real-key"
    assert sent["headers"]["anthropic-version"] == "2023-06-01"
    assert sent["body"]["model"] == "claude-sonnet-4-5"
    assert sent["body"]["max_tokens"] == 50

    assert proc.poll() is None


def test_unconfigured_resolved_connector_returns_503_never_501_or_a_silent_200(tmp_path, node_server):
    spec = _spec_with_integrations(["Anthropic"])
    generate_app(spec, tmp_path)
    proc, base_url = node_server(tmp_path)  # no ANTHROPIC_API_KEY in env
    status, body = _post(f"{base_url}/api/integrations/anthropic", {"model": "x", "messages": []})
    assert status == 503
    assert body["status"] == "error"
    assert "ANTHROPIC_API_KEY" in body["error"]
    assert "test-only" not in body["error"]  # no key material, obviously, since none was ever set


def test_provider_401_maps_to_503_connector_auth_error_no_key_echoed(tmp_path, node_server, mock_provider):
    mock_provider.set_response(
        401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    )
    spec = _spec_with_integrations(["Anthropic"])
    generate_app(spec, tmp_path)
    proc, base_url = node_server(
        tmp_path,
        extra_env={"ANTHROPIC_API_KEY": "definitely-not-a-real-secret-value", "ANTHROPIC_API_BASE_URL": mock_provider.base_url},
    )
    status, body = _post(f"{base_url}/api/integrations/anthropic", {"model": "x", "messages": [{"role": "user", "text": "hi"}]})
    assert status == 503
    assert "definitely-not-a-real-secret-value" not in json.dumps(body)


def test_provider_429_maps_to_429_and_the_generated_app_still_answers_health(tmp_path, node_server, mock_provider):
    mock_provider.set_response(
        429,
        {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}},
        headers={"Retry-After": "7"},
    )
    spec = _spec_with_integrations(["Anthropic"])
    generate_app(spec, tmp_path)
    proc, base_url = node_server(
        tmp_path, extra_env={"ANTHROPIC_API_KEY": "test-key", "ANTHROPIC_API_BASE_URL": mock_provider.base_url}
    )
    status, _ = _post(f"{base_url}/api/integrations/anthropic", {"model": "x", "messages": [{"role": "user", "text": "hi"}]})
    assert status == 429
    # A connector failure never takes down the rest of the app.
    health_status, health_body = _get(f"{base_url}/health")
    assert health_status == 200
    assert health_body == {"status": "ok"}
    assert proc.poll() is None


# --------------------------------------------------------------------------
# Cyra LOW F6 (PR #84 security review, fix-up round) — `base_url_override_env`
# is now https-pinned at runtime: an http:// override is refused (fail
# CLOSED, never a silent cleartext send), an https:// override still works
# exactly as before. Both proven end-to-end, real subprocess + real network
# I/O, not a source-inspection assertion.
# --------------------------------------------------------------------------


def test_http_base_url_override_is_refused_before_any_network_call(tmp_path, node_server):
    """A plain http:// override must be refused with a typed config error
    (503) — and, critically, the refusal happens BEFORE any request is
    sent: a genuinely local, plain-HTTP mock server is started here and
    asserted to receive ZERO requests, proving this is fail-CLOSED
    (refuse-then-never-call), not fail-open-then-log."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            self.rfile.read(length) if length else b""
            received.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"should":"never be sent"}')

        def log_message(self, *a):
            pass

    plain_http_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=plain_http_server.serve_forever, daemon=True)
    thread.start()
    port = plain_http_server.server_address[1]
    try:
        spec = _spec_with_integrations(["Anthropic"])
        generate_app(spec, tmp_path)
        proc, base_url = node_server(
            tmp_path,
            extra_env={
                "ANTHROPIC_API_KEY": "test-only-not-a-real-key",
                "ANTHROPIC_API_BASE_URL": f"http://127.0.0.1:{port}",  # plain HTTP -- must be refused
            },
        )
        status, body = _post(
            f"{base_url}/api/integrations/anthropic",
            {"model": "x", "messages": [{"role": "user", "text": "hi"}], "max_tokens": 10},
        )
        assert status == 503, body
        assert body["status"] == "error"
        assert "https" in body["error"].lower()
        assert "ANTHROPIC_API_BASE_URL" in body["error"]
        # No key material echoed in the refusal, same discipline as every
        # other config-error message this client throws.
        assert "test-only-not-a-real-key" not in json.dumps(body)
        # The whole point: refused BEFORE any network call ever happens.
        assert received == []
        assert proc.poll() is None
    finally:
        plain_http_server.shutdown()
        thread.join(timeout=5)


def test_https_base_url_override_still_works(tmp_path, node_server, mock_provider):
    """The other half: an `https://` override is NOT rejected by the new
    guard — a full, genuine round trip against the real (self-signed) TLS
    mock provider, same shape as
    `test_anthropic_connector_boots_and_round_trips_over_real_http` above,
    proving the https-pin fix didn't also break the legitimate case."""
    assert mock_provider.base_url.startswith("https://")
    mock_provider.set_response(
        200,
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello over real HTTPS"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 3},
        },
    )
    spec = _spec_with_integrations(["Anthropic"])
    generate_app(spec, tmp_path)
    proc, base_url = node_server(
        tmp_path,
        extra_env={"ANTHROPIC_API_KEY": "test-only-not-a-real-key", "ANTHROPIC_API_BASE_URL": mock_provider.base_url},
    )
    status, body = _post(
        f"{base_url}/api/integrations/anthropic",
        {"model": "claude-sonnet-4-5", "messages": [{"role": "user", "text": "hi"}], "max_tokens": 10},
    )
    assert status == 200, body
    assert body["status"] == "ok"
    assert body["output"]["text"] == "Hello over real HTTPS"
    assert len(mock_provider.requests) == 1
    assert proc.poll() is None


def test_openai_and_gemini_connectors_also_round_trip_for_real(tmp_path, node_server, _self_signed_cert):
    """Coverage for the OTHER two v1 provider templates (not just
    Anthropic) — different auth header, different body shape, different
    response shape, each against its OWN mocked provider."""
    openai_mock = None
    gemini_mock = None
    try:
        openai_mock = _start_mock(
            200,
            {
                "id": "chatcmpl-x",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi from OpenAI mock"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
            },
            _self_signed_cert,
        )
        gemini_mock = _start_mock(
            200,
            {
                "candidates": [{"content": {"role": "model", "parts": [{"text": "Hi from Gemini mock"}]}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 2},
            },
            _self_signed_cert,
        )

        spec = _spec_with_integrations(["OpenAI", "Gemini"])
        generate_app(spec, tmp_path)
        proc, base_url = node_server(
            tmp_path,
            extra_env={
                "OPENAI_API_KEY": "test-openai-key",
                "OPENAI_API_BASE_URL": openai_mock["base_url"],
                "GEMINI_API_KEY": "test-gemini-key",
                "GEMINI_API_BASE_URL": gemini_mock["base_url"],
            },
        )

        status, body = _post(
            f"{base_url}/api/integrations/openai",
            {"model": "gpt-4o-mini", "messages": [{"role": "user", "text": "hi"}], "max_tokens": 20},
        )
        assert status == 200, body
        assert body["output"]["text"] == "Hi from OpenAI mock"
        assert openai_mock["requests"][0]["headers"]["authorization"] == "Bearer test-openai-key"
        assert openai_mock["requests"][0]["path"] == "/v1/chat/completions"

        status, body = _post(
            f"{base_url}/api/integrations/gemini",
            {"model": "gemini-2.5-flash", "messages": [{"role": "user", "text": "hi"}], "max_tokens": 20},
        )
        assert status == 200, body
        assert body["output"]["text"] == "Hi from Gemini mock"
        assert gemini_mock["requests"][0]["headers"]["x-goog-api-key"] == "test-gemini-key"
        assert gemini_mock["requests"][0]["path"] == "/v1beta/models/gemini-2.5-flash:generateContent"

        assert proc.poll() is None
    finally:
        for mock in (openai_mock, gemini_mock):
            if mock is not None:
                mock["server"].shutdown()
                mock["thread"].join(timeout=5)


def _start_mock(status, body, self_signed_cert, headers=None):
    """Standalone (non-fixture) helper for the multi-mock test above —
    same loopback-only, request-recording HTTPS server as the
    `mock_provider` fixture (same `_self_signed_cert`), returned as a
    plain dict so the test can start >1 instance."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            received.append(
                {
                    "path": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": json.loads(raw) if raw else None,
                }
            )
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    cert_path, key_path = self_signed_cert
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(str(cert_path), str(key_path))
    server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return {"server": server, "thread": thread, "base_url": f"https://127.0.0.1:{port}", "requests": received}
