"""Public snapshot HTTP service and separate loopback-only lifecycle service."""
import hmac
import io
import ipaddress
import json
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from content import PreviewError, safe_relative

HEADER_SECONDS = 3
RESPONSE_SECONDS = 5


class DeadlineReader(io.RawIOBase):
    """Recompute remaining wall-clock budget on EVERY recv, not inactivity."""
    def __init__(self, connection):
        super().__init__()
        self.connection = connection
        self.deadline = time.monotonic() + HEADER_SECONDS

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Request header deadline exceeded")
        self.connection.settimeout(remaining)
        return self.connection.recv_into(buffer)


def wsl_mode():
    """Query actual active mode, not a requested .wslconfig setting."""
    release = os.uname().release.lower() if os.name == "posix" else ""
    if "microsoft" not in release and not os.environ.get("WSL_DISTRO_NAME"):
        return None
    try:
        value = subprocess.check_output(["/usr/bin/wslinfo", "--networking-mode"],
                                        timeout=3, text=True).strip().lower()
        return value if value in {"nat", "mirrored", "none", "wsl1", "bridged", "virtioproxy", "consomme"} else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def network_status():
    """Use current interfaces; WSL NAT guests are NOT LAN host addresses."""
    mode = wsl_mode()
    if mode is not None and mode != "mirrored":
        return {"address": None, "wsl_mode": mode,
                "limitation": "WSL networking mode " + mode +
                ": guest-local HTTP does not establish a LAN route. Only localhost is offered; no portproxy/firewall change was made."}
    try:
        if __import__("sys").platform == "darwin":
            output = subprocess.check_output(["/sbin/ifconfig"], timeout=3, text=True)
            candidates = [line.split()[1] for line in output.splitlines()
                          if line.strip().startswith("inet ")]
        else:
            output = subprocess.check_output(["ip", "-j", "-4", "addr", "show", "up"],
                                             timeout=3, text=True)
            candidates = [a["local"] for i in json.loads(output) for a in i.get("addr_info", [])
                          if a.get("family") == "inet" and a.get("scope") == "global"]
        for candidate in candidates:
            addr = ipaddress.IPv4Address(candidate)
            if not (addr.is_loopback or addr.is_link_local or addr.is_unspecified or addr.is_multicast):
                return {"address": str(addr), "wsl_mode": mode,
                        "limitation": "WSL mirrored interface candidate only; firewall and second-device reachability remain unverified."
                        if mode == "mirrored" else None}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        pass
    return {"address": None, "wsl_mode": mode, "limitation": "No usable LAN IPv4 interface detected; only localhost is offered."}


def lan_ip():
    return network_status()["address"]


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, *args, **kwargs):
        self.capacity = threading.BoundedSemaphore(16)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.capacity.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.capacity.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.capacity.release()

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(5)
        return request, address


def bind(host, preferred, handler):
    try:
        return Server((host, preferred), handler)
    except OSError as error:
        import errno
        if preferred and error.errno == errno.EADDRINUSE:
            return Server((host, 0), handler)
        raise


class QuietHandler(BaseHTTPRequestHandler):
    server_version = "TessPreview"
    sys_version = ""

    def setup(self):
        super().setup()
        self.rfile.close()
        self.rfile = io.BufferedReader(DeadlineReader(self.connection))

    def log_message(self, format, *args):
        # Never log arbitrary URL/query/header input or bearer credentials.
        pass

    def reply(self, code, data=b"Not available\n", mime="text/plain", head=False, location=None):
        deadline = time.monotonic() + RESPONSE_SECONDS
        self.connection.settimeout(RESPONSE_SECONDS)
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        if location:
            self.send_header("Location", location)
        self.end_headers()
        if not head:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Response deadline exceeded")
            # sendall's timeout is the total write budget, not a per-byte reset.
            self.connection.settimeout(remaining)
            self.wfile.write(data)

    def send_error(self, code, message=None, explain=None):
        self.reply(code)


def public_handler(slug, assets, spa):
    prefix = "/dev/" + slug

    class Public(QuietHandler):
        def do_GET(self):
            self.get(False)

        def do_HEAD(self):
            self.get(True)

        def get(self, head):
            try:
                path = unquote(urlsplit(self.path).path, errors="strict")
                # Reject double encoding, encoded separators, controls, traversal.
                raw_path = urlsplit(self.path).path.lower()
                if any(x in raw_path for x in ("%2f", "%5c")) or "%" in path or "\\" in path:
                    raise PreviewError("Invalid route")
                if path == prefix:
                    return self.reply(308, b"", head=head, location=prefix + "/")
                if not path.startswith(prefix + "/"):
                    return self.reply(404, head=head)
                relative = path[len(prefix) + 1:]
                if not relative:
                    relative = "index.html"
                else:
                    safe_relative(relative.rstrip("/"))
                asset = assets.get(relative)
                if asset is None and spa and "." not in relative.split("/")[-1]:
                    asset = assets["index.html"]
                if asset is None:
                    return self.reply(404, head=head)
                return self.reply(200, asset[0], asset[1], head)
            except (PreviewError, ValueError, UnicodeError):
                return self.reply(404, head=head)

    return Public


def control_handler(record, public_server):
    class Control(QuietHandler):
        def authorized(self):
            value = self.headers.get("Authorization", "")
            return hmac.compare_digest(value, "Bearer " + record["token"])

        def do_GET(self):
            if self.path != "/status" or not self.authorized():
                return self.reply(404)
            body = json.dumps({"instance": record["instance"], "pid": os.getpid()}).encode()
            self.reply(200, body, "application/json")

        def do_POST(self):
            if self.path != "/stop" or not self.authorized():
                return self.reply(404)
            self.reply(200, b"Stopped\n")
            threading.Thread(target=public_server.shutdown, daemon=True).start()

    return Control
