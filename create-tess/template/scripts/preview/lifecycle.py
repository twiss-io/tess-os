"""Detached processes with lock ownership and authenticated stop, never PID kill."""
import hashlib
import http.client
import json
import os
import secrets
import select
import stat
import subprocess
import sys
import threading
import time

if os.name == "posix":
    import fcntl

from content import PreviewError, directory, snapshot
from server import bind, control_handler, lan_ip, public_handler


def private_file(root, name, flags):
    fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=root)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        raise PreviewError("Unsafe preview state file; refusing access.")
    return fd


def read_record(state_dir, slug):
    with directory(state_dir, private=True) as root:
        fd = private_file(root, slug + ".json", os.O_RDONLY)
        with os.fdopen(fd, "r") as stream:
            record = json.loads(stream.read(256 * 1024))
    if record.get("slug") != slug or not isinstance(record.get("token"), str):
        raise PreviewError("Invalid preview state.")
    return record


def write_record(root, slug, record):
    temp = slug + "." + secrets.token_hex(8) + ".tmp"
    fd = private_file(root, temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(record, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temp, slug + ".json", src_dir_fd=root, dst_dir_fd=root)
    finally:
        try:
            os.unlink(temp, dir_fd=root)
        except FileNotFoundError:
            pass


def control(record, action="status"):
    connection = http.client.HTTPConnection("127.0.0.1", record["control_port"], timeout=3)
    try:
        method = "POST" if action == "stop" else "GET"
        connection.request(method, "/" + action, headers={"Authorization": "Bearer " + record["token"]})
        response = connection.getresponse()
        data = response.read(4096)
        if response.status != 200:
            raise PreviewError("Preview ownership could not be authenticated; no process was signaled.")
        if action == "status":
            status = json.loads(data)
            if status != {"instance": record["instance"], "pid": record["pid"]}:
                raise PreviewError("Preview identity changed; no process was signaled.")
        return True
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise PreviewError("Preview is stopped or stale; no process was signaled.") from error
    finally:
        connection.close()


def stop(record):
    control(record)
    control(record, "stop")
    # Wait for our lock, NOT for a PID (which might already have been reused).
    with directory(record["config"]["state_dir"], private=True) as root:
        fd = private_file(root, record["slug"] + ".lock", os.O_RDWR)
        try:
            for _ in range(100):
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except BlockingIOError:
                    time.sleep(0.05)
            raise PreviewError("Stop was requested but shutdown is not confirmed; retry status.")
        finally:
            os.close(fd)


def start(config, script):
    with directory(config["state_dir"], create=True, private=True) as root:
        log_fd = private_file(root, config["slug"] + ".log", os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        child = subprocess.Popen(
            [sys.executable, script, "_serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=log_fd, start_new_session=True, close_fds=True, cwd="/",
        )
    finally:
        os.close(log_fd)
    child.stdin.write(json.dumps(config).encode())
    child.stdin.close()
    if not select.select([child.stdout], [], [], 15)[0]:
        child.stdout.close()
        raise PreviewError("Startup not confirmed; check status/logs before retrying. No PID was killed.")
    line = child.stdout.readline(256 * 1024)
    child.stdout.close()
    if not line:
        child.wait(timeout=3)
        raise PreviewError("Preview startup refused; inspect its private log.")
    ready = json.loads(line)
    record = read_record(config["state_dir"], config["slug"])
    if ready.get("instance") != record["instance"] or record["pid"] != child.pid:
        raise PreviewError("Concurrent launch identity mismatch; check status. No PID was killed.")
    control(record)
    return record


def serve(config):
    public = management = None
    with directory(config["state_dir"], private=True) as root:
        lock = private_file(root, config["slug"] + ".lock", os.O_RDWR | os.O_CREAT)
        try:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise PreviewError("This project slug already has a running preview.") from error
            assets = snapshot(config["public_dir"], config["files"])
            host = "127.0.0.1" if config["localhost_only"] else "0.0.0.0"
            public = bind(host, config["port"], public_handler(config["slug"], assets, config["spa"]))
            record = {
                "slug": config["slug"], "pid": os.getpid(), "instance": secrets.token_hex(24),
                "token": secrets.token_hex(32), "host": host,
                "port": public.server_address[1], "config": config,
                "assets": {name: data[2] for name, data in assets.items()},
                "snapshot_bytes": sum(len(data[0]) for data in assets.values()),
            }
            management = bind("127.0.0.1", 0, control_handler(record, public))
            record["control_port"] = management.server_address[1]
            write_record(root, config["slug"], record)
            threading.Thread(target=management.serve_forever, daemon=True).start()
            print(json.dumps({"instance": record["instance"]}), flush=True)
            print("Preview started; snapshot immutable until restart.", file=sys.stderr, flush=True)
            public.serve_forever(poll_interval=0.1)
        finally:
            if public:
                public.server_close()
            if management:
                management.shutdown()
                management.server_close()
            os.close(lock)
            print("Preview process exited.", file=sys.stderr, flush=True)


def fetch(host, port, path):
    connection = http.client.HTTPConnection(host, port, timeout=3)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.getheader("Location"), response.read(16 * 1024 * 1024 + 1)
    finally:
        connection.close()


def verify(record):
    control(record)
    address = None if record["host"] == "127.0.0.1" else lan_ip()
    hosts = ["127.0.0.1"] + ([address] if address else [])
    prefix = "/dev/" + record["slug"]
    denied = ["/.git/config", "/.env", "/kb/private.html", "/.tess/state",
              "/../index.html", "/%2e%2e/index.html", "/%252e%252e/index.html",
              "/assets%2fsecret.html", "/assets/", "/unknown.js"]
    for host in hosts:
        if fetch(host, record["port"], prefix)[:2] != (308, prefix + "/"):
            raise PreviewError("Preview trailing-slash verification failed.")
        code, _, body = fetch(host, record["port"], prefix + "/")
        if code != 200 or hashlib.sha256(body).hexdigest() != record["assets"]["index.html"]:
            raise PreviewError("Preview entry-point verification failed.")
        for name, digest in record["assets"].items():
            code, _, body = fetch(host, record["port"], prefix + "/" + name)
            if code != 200 or hashlib.sha256(body).hexdigest() != digest:
                raise PreviewError("A required preview asset failed verification.")
        code, _, body = fetch(host, record["port"], prefix + "/verify/deep-link")
        expected = 200 if record["config"]["spa"] else 404
        if code != expected or (expected == 200 and hashlib.sha256(body).hexdigest() != record["assets"]["index.html"]):
            raise PreviewError("Preview deep-link verification failed.")
        for suffix in denied:
            # For an SPA an extensionless directory can return the explicit index,
            # never a listing; use the non-SPA asset directory probe otherwise.
            if suffix == "/assets/" and record["config"]["spa"]:
                continue
            if fetch(host, record["port"], prefix + suffix)[0] != 404:
                raise PreviewError("Preview private-path denial verification failed.")
        for outside in ("/", "/dev/other-project/index.html", "/.tess/state"):
            if fetch(host, record["port"], outside)[0] != 404:
                raise PreviewError("Preview project isolation verification failed.")
    return hosts
