#!/usr/bin/env python3
"""Apply the CPython 3.13 correction for CVE-2026-82049 to an installed stdlib.

The pinned base images ship CPython 3.13.15, whose ``tarfile`` ``data``/``tar``
extraction filters follow a hard link to a symbolic link outside the
destination directory. The fix (python/cpython ``b8f23e3``) is on the ``3.13``
branch but not in any released 3.13.x, so the image build installs it here.

This is deliberately not GNU ``patch``: the target must be byte-identical to
the ``Lib/tarfile.py`` of the v3.13.15 tag before the edit and byte-identical
to the expected result afterwards. Any other input fails the build, which is
the intended expiry: the moment the base image moves to a release that already
carries the fix, this step and the matching ``.grype.yaml`` entry must be
removed together (see ``security/python313/README.md``).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

CVE = "CVE-2026-82049"
UPSTREAM_COMMIT = "b8f23e307097552eaea2604383a12ab280520d0d"
DEFAULT_TARGET = Path("/usr/local/lib/python3.13/tarfile.py")
# sha256 of Lib/tarfile.py at tag v3.13.15 == the file in python:3.13.15-*-bookworm.
BEFORE_SHA256 = "9fedddf7e814c226cb7e1ac0aa603092eda40047367ec00ad740a81484a17d01"
AFTER_SHA256 = "7ad04a66bb92373bd6d2552a2f01fce8a4ca95463ebf661612fd574465977929"
OLD = b"                    os.link(tarinfo._link_target, targetpath)\n"
NEW = (
    b"                    # Resolve the target so the hard link points to the file\n"
    b"                    # itself. Otherwise os.link() may duplicate a symlink to a\n"
    b"                    # shallower location, where it's relative target escapes the\n"
    b"                    # destination directory. (CVE-2026-82049)\n"
    b"                    os.link(os.path.realpath(tarinfo._link_target), targetpath)\n"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patched_bytes(original: bytes) -> bytes:
    """Return the corrected file, refusing anything but the pinned 3.13.15 bytes."""
    digest = sha256(original)
    if digest == AFTER_SHA256:
        raise SystemExit(f"{CVE}: correction already present (sha256 {digest})")
    if digest != BEFORE_SHA256:
        raise SystemExit(
            f"{CVE}: refusing to patch an unpinned tarfile.py (sha256 {digest}, "
            f"expected {BEFORE_SHA256}); if the base image is no longer 3.13.15 remove "
            "this step and the .grype.yaml entry together"
        )
    if original.count(OLD) != 1:
        raise SystemExit(f"{CVE}: vulnerable line not found exactly once")
    result = original.replace(OLD, NEW)
    if sha256(result) != AFTER_SHA256:
        raise SystemExit(f"{CVE}: patched digest mismatch ({sha256(result)})")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args(argv)
    target: Path = args.target
    result = patched_bytes(target.read_bytes())
    target.write_bytes(result)
    for stale in (target.parent / "__pycache__").glob(f"{target.stem}.*.pyc"):
        stale.unlink()
    print(f"{CVE}=APPLIED target={target} sha256={AFTER_SHA256} upstream={UPSTREAM_COMMIT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
