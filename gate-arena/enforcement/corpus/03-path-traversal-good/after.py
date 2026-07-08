import os


def resolve_upload_path(filename, base_dir):
    base = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base, filename))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("path traversal attempt rejected")
    return target
