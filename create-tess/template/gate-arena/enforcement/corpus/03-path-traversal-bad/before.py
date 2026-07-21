import os


def resolve_upload_path(filename, base_dir):
    return os.path.join(base_dir, filename)
