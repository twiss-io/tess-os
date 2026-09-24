#!/usr/bin/env python3
"""A local stand-in for an OpenAI-compatible Chat Completions endpoint.

The runtime smoke points a coding-agent CLI at this server instead of a vendor
model. Every request body is appended to a JSONL log, so the smoke can read
exactly what the CLI sent as the model's context: which instruction files it
loaded, which skills it listed, which tools it offered. No login, no API key
and no model call are involved. Stdlib only; Python 3.9+.

Replies are fixed. An optional script makes the server answer the first
request that offers a named tool with a call to that tool (used by the Grok
gate probe); every other request gets plain text.

Run it on its own with:
    python3 mock_llm.py --log requests.jsonl --port-file port.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPLY = "MOCK-REPLY: request recorded by tools/runtime-smoke."


def _chunk(model: str, created: int, delta: dict, finish=None) -> bytes:
    evt = {"id": "mock-1", "object": "chat.completion.chunk", "created": created,
           "model": model, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if finish is not None:
        evt["usage"] = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    return ("data: " + json.dumps(evt) + "\n\n").encode()


def _completion(model: str, created: int, message: dict, finish: str) -> dict:
    return {"id": "mock-1", "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


def make_handler(log_path: str, script=None):
    """Build a request handler class bound to one log file and one script."""
    lock = threading.Lock()
    pending = list(script or [])  # [{"tool": name, "arguments": {...}}], each served once

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep the smoke's stderr clean
            return

        def _send_json(self, code: int, obj: dict) -> None:
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _stream(self, chunks) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            for chunk in chunks:
                self.wfile.write(chunk)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True

        def _take_scripted_call(self, body: dict):
            offered = {(t.get("function") or {}).get("name") for t in body.get("tools") or []}
            with lock:
                for i, step in enumerate(pending):
                    if step.get("tool") in offered:
                        return pending.pop(i)
            return None

        def do_GET(self):
            if self.path.rstrip("/").endswith("/models"):
                self._send_json(200, {"object": "list", "data": [
                    {"id": "mock-model", "object": "model", "owned_by": "tess-runtime-smoke"}]})
            else:
                self._send_json(404, {"error": {"message": "not found"}})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {"_raw": raw[:2000].decode("utf-8", "replace")}
            with lock, open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"path": self.path, "body": body}) + "\n")
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self._send_json(404, {"error": {"message": "only chat/completions is mocked"}})
                return
            self._answer(body)

        def _answer(self, body: dict) -> None:
            model, created = body.get("model", "mock-model"), int(time.time())
            call = self._take_scripted_call(body)
            if call is not None:
                args = json.dumps(call.get("arguments") or {})
                tc = {"id": "call_smoke_1", "type": "function",
                      "function": {"name": call["tool"], "arguments": args}}
                if body.get("stream"):
                    first = {"index": 0, "id": tc["id"], "type": "function",
                             "function": {"name": call["tool"], "arguments": ""}}
                    self._stream([
                        _chunk(model, created, {"role": "assistant", "content": None, "tool_calls": [first]}),
                        _chunk(model, created, {"tool_calls": [{"index": 0, "function": {"arguments": args}}]}),
                        _chunk(model, created, {}, finish="tool_calls")])
                else:
                    msg = {"role": "assistant", "content": None, "tool_calls": [tc]}
                    self._send_json(200, _completion(model, created, msg, "tool_calls"))
                return
            if body.get("stream"):
                self._stream([_chunk(model, created, {"role": "assistant", "content": ""}),
                              _chunk(model, created, {"content": REPLY}),
                              _chunk(model, created, {}, finish="stop")])
            else:
                msg = {"role": "assistant", "content": REPLY}
                self._send_json(200, _completion(model, created, msg, "stop"))

    return Handler


class MockServer:
    """Context manager: a mock endpoint on 127.0.0.1, served from a thread."""

    def __init__(self, log_path: str, script=None):
        self.log_path = log_path
        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(log_path, script))
        self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return "http://127.0.0.1:%d/v1" % self._srv.server_address[1]

    def __enter__(self) -> "MockServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._srv.shutdown()
        self._srv.server_close()

    def requests(self) -> list:
        try:
            with open(self.log_path, encoding="utf-8") as fh:
                return [json.loads(line)["body"] for line in fh if line.strip()]
        except FileNotFoundError:
            return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--log", required=True, help="JSONL file that receives every request body")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--port-file", required=True, help="the bound port is written here")
    ap.add_argument("--script", help="JSON list of {tool, arguments} calls to return once each")
    args = ap.parse_args()
    script = None
    if args.script:
        with open(args.script, encoding="utf-8") as fh:
            script = json.load(fh)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.log, script))
    with open(args.port_file, "w", encoding="utf-8") as fh:
        fh.write(str(srv.server_address[1]))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
