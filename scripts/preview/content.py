"""Explicit public-file snapshots; never resolve HTTP requests against disk."""
import contextlib
import hashlib
import os
import re
import stat
from pathlib import Path

MAX_FILES = 512
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
PRIVATE = {
    "kb", "brain", "private", "credentials", "secrets", "node_modules",
    "conductor", "operator", "admin", "claude.md", "agents.md", "gemini.md",
    "package.json", "package-lock.json", "tess.manifest.json",
}
PRIVATE_STEMS = {"credential", "credentials", "secret", "secrets", "password", "passwords",
                 "token", "tokens", "vault", "id_rsa", "id_ed25519", "settings", "config"}
MIME = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp", ".avif": "image/avif", ".ico": "image/x-icon",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf",
    ".otf": "font/otf", ".mp4": "video/mp4", ".webm": "video/webm",
    ".mp3": "audio/mpeg", ".wav": "audio/wav",
}


class PreviewError(Exception):
    """User-safe error; never disclose a source path over HTTP."""


def require_platform():
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise PreviewError("Use macOS, Linux, or Windows WSL; native Windows is not supported.")


def safe_relative(name):
    parts = name.split("/")
    if not parts or any(not COMPONENT.fullmatch(p) or p.lower() in PRIVATE or
                        p.lower().split(".", 1)[0] in PRIVATE_STEMS for p in parts):
        raise PreviewError("Only non-hidden, non-private public paths are permitted.")
    return parts


@contextlib.contextmanager
def directory(path, create=False, private=False):
    """Walk from / using openat + O_NOFOLLOW, retaining directory identity.

    Symlink ancestors (including aliases such as macOS /var) are rejected:
    callers must supply the physical path. No string-prefix containment check.
    """
    require_platform()
    path = Path(os.path.abspath(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if private and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise PreviewError("Preview state directory must be owned by you with mode 0700.")
        yield fd
    finally:
        os.close(fd)


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def read_public(root_fd, name):
    parts = safe_relative(name)
    if Path(name).suffix.lower() not in MIME:
        raise PreviewError("File type is not a supported public preview asset.")
    parent = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise PreviewError("Only regular, non-hardlinked public files are permitted.")
            if before.st_size > MAX_FILE_BYTES:
                raise PreviewError("A preview asset exceeds the 16 MiB limit.")
            chunks, remaining = [], MAX_FILE_BYTES + 1
            while remaining:
                chunk = os.read(fd, min(remaining, 1024 * 1024))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > MAX_FILE_BYTES or identity(before) != identity(os.fstat(fd)):
                raise PreviewError("Public files changed during snapshot; retry after the build settles.")
            return data
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def snapshot(public_dir, files):
    if not files or len(files) > MAX_FILES or len(set(files)) != len(files):
        raise PreviewError("Select 1 to 512 unique public files explicitly with --file.")
    if "index.html" not in files:
        raise PreviewError("Select index.html explicitly; it is the preview entry point.")
    result, total = {}, 0
    with directory(public_dir) as root:
        # Even with an allowlist, refuse common broad/private roots.
        if Path(os.path.abspath(public_dir)) in (Path("/"), Path.home()):
            raise PreviewError("Use an isolated public build directory, not a home or filesystem root.")
        for marker in (".git", ".tess", "AGENTS.md", "CLAUDE.md", "brain", "kb", ".env"):
            try:
                os.stat(marker, dir_fd=root, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise PreviewError("Use an isolated public build directory, not a workspace/private root.")
        for name in files:
            data = read_public(root, name)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise PreviewError("Preview snapshot exceeds the 64 MiB total limit.")
            result[name] = (data, MIME[Path(name).suffix.lower()], hashlib.sha256(data).hexdigest())
    return result
