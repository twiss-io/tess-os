import os


def resolve_upload_path(filename, base_dir):
    # Looks like a fix (blocks the literal ".." substring) but misses the
    # OTHER escape route entirely: os.path.join(base, filename) discards
    # `base` outright whenever `filename` is an ABSOLUTE path — so
    # "/etc/passwd" sails through untouched, no ".." required.
    if ".." in filename:
        raise ValueError("path traversal attempt rejected")
    return os.path.join(base_dir, filename)
