"""Read bounded release artifacts through a directory descriptor."""

from contextlib import ExitStack
import hashlib
import os
from pathlib import PurePosixPath
import stat

from .backends import MAX_RESPONSE_BYTES


def read_artifact(root: str, relative_path: str, expected_digest: str) -> bytes:
    """Open only regular files below the mounted root, without following links.

    Both paths come from release configuration, never directly from the request.
    Descriptor-relative opens keep containment valid while directories change.
    """
    path = PurePosixPath(relative_path)
    if path.is_absolute() or not path.parts or any(p == ".." for p in path.parts):
        raise ValueError("artifact must have a relative path inside its root")
    with ExitStack() as stack:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, directory)
        for part in path.parts[:-1]:
            directory = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            stack.callback(os.close, directory)
        descriptor = os.open(
            path.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("artifact must be a regular file")
            raw = stream.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("artifact exceeds size limit")
    if "sha256:" + hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError("artifact digest mismatch")
    return raw
