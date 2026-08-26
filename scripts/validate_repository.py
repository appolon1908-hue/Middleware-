#!/usr/bin/env python3
"""Fail-closed bootstrap validation for the Codestra middleware repository.

This validator is intentionally dependency-free so it can run before the live
middleware's package manager and lock files are imported. It is a guardrail,
not a replacement for a dedicated secret scanner, SAST, dependency audit,
container scan, or application integration tests.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 10 * 1024 * 1024

REQUIRED_FILES = (
    Path("README.md"),
    Path(".gitignore"),
    Path(".dockerignore"),
    Path("config/preproduction-safety.env.example"),
)

FORBIDDEN_TOP_LEVEL_DIRECTORIES = {
    "backups",
    "credentials",
    "private-evidence",
    "runtime",
    "secrets",
}

FORBIDDEN_SUFFIXES = {
    ".aof",
    ".backup",
    ".dump",
    ".har",
    ".jks",
    ".key",
    ".keystore",
    ".p12",
    ".pcap",
    ".pem",
    ".pfx",
    ".rdb",
    ".sqlite",
    ".sqlite3",
    ".trace",
}

SECRET_PATTERNS = {
    "private key material": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "AWS access key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
}

EXPECTED_SAFETY_VALUES = {
    "APP_ENV": "staging",
    "SEND_EVENTS": "false",
    "ENABLE_EXTERNAL_DELIVERY": "false",
    "LIVE_WRITE": "false",
    "LIVE_WRITES": "false",
    "ODOO_WRITE": "false",
    "CALLBACK_DISPATCH": "false",
    "N8N_DELIVERY_ENABLED": "false",
    "VICIDIAL_WRITES_ENABLED": "false",
    "EXTERNAL_DIAL_ENABLED": "false",
    "PRODUCTION_CALLBACKS_ENABLED": "false",
    "N8N_PRODUCTION_WORKFLOWS_ENABLED": "false",
    "PRODUCTION_DIALING": "DISABLED",
}

ACTION_REF_RE = re.compile(
    r"^\s*-?\s*uses:\s*([^\s#]+)(?:\s*#.*)?$", re.MULTILINE
)
FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def is_allowed_env_example(path: Path) -> bool:
    name = path.name
    return name == ".env.example" or name.endswith(".env.example")


def iter_repository_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if ".git" in relative.parts:
            continue
        if path.is_file() or path.is_symlink():
            files.append(path)
    return sorted(files)


def validate_required_files(errors: list[str]) -> None:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required bootstrap file: {relative}")


def validate_paths(files: list[Path], errors: list[str]) -> None:
    for path in files:
        relative = path.relative_to(ROOT)

        if path.is_symlink():
            try:
                target = path.resolve(strict=False)
                target.relative_to(ROOT)
            except ValueError:
                errors.append(f"symlink escapes repository: {relative} -> {path.readlink()}")

        if relative.parts and relative.parts[0] in FORBIDDEN_TOP_LEVEL_DIRECTORIES:
            errors.append(f"forbidden top-level runtime/secret path: {relative}")

        if path.name.startswith(".env") and not is_allowed_env_example(path):
            errors.append(f"live environment file must not be committed: {relative}")

        lower_name = path.name.lower()
        if any(lower_name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
            errors.append(f"forbidden secret/runtime file type: {relative}")

        try:
            size = path.stat().st_size
        except OSError as exc:
            errors.append(f"cannot stat {relative}: {exc}")
            continue
        if size > MAX_FILE_BYTES:
            errors.append(
                f"file exceeds {MAX_FILE_BYTES // (1024 * 1024)} MiB bootstrap limit: "
                f"{relative} ({size} bytes)"
            )


def validate_file_contents(files: list[Path], errors: list[str]) -> None:
    for path in files:
        relative = path.relative_to(ROOT)
        if path.is_symlink():
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read {relative}: {exc}")
            continue

        if b"\x00" in data:
            continue

        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                errors.append(f"possible {label} committed in: {relative}")


def parse_env_example(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"line {line_number} is not KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"line {line_number} has invalid variable name {key!r}")
        if key in values:
            raise ValueError(f"line {line_number} duplicates variable {key}")
        values[key] = value.strip()
    return values


def validate_safety_baseline(errors: list[str]) -> None:
    path = ROOT / "config/preproduction-safety.env.example"
    if not path.is_file():
        return
    try:
        values = parse_env_example(path)
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"invalid preproduction safety baseline: {exc}")
        return

    for key, expected in EXPECTED_SAFETY_VALUES.items():
        actual = values.get(key)
        if actual != expected:
            errors.append(
                f"unsafe or missing baseline value: {key}={actual!r}; "
                f"expected {expected!r}"
            )


def validate_workflow_pinning(errors: list[str]) -> None:
    workflow_dir = ROOT / ".github" / "workflows"
    if not workflow_dir.is_dir():
        errors.append("missing .github/workflows directory")
        return

    workflow_files = sorted(
        path
        for pattern in ("*.yml", "*.yaml")
        for path in workflow_dir.glob(pattern)
    )
    if not workflow_files:
        errors.append("no GitHub Actions workflow is present")
        return

    for path in workflow_files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot read workflow {path.relative_to(ROOT)}: {exc}")
            continue

        for match in ACTION_REF_RE.finditer(text):
            action = match.group(1).strip("\"'")
            if action.startswith("./"):
                continue
            if action.startswith("docker://"):
                image_ref = action.removeprefix("docker://")
                if "@sha256:" not in image_ref:
                    errors.append(
                        f"container action is not digest-pinned in "
                        f"{path.relative_to(ROOT)}: {action}"
                    )
                continue
            if "@" not in action:
                errors.append(
                    f"action has no immutable ref in {path.relative_to(ROOT)}: {action}"
                )
                continue
            _, ref = action.rsplit("@", 1)
            if not FULL_SHA_RE.fullmatch(ref):
                errors.append(
                    f"action is not pinned to a 40-character commit SHA in "
                    f"{path.relative_to(ROOT)}: {action}"
                )


def main() -> int:
    errors: list[str] = []
    files = iter_repository_files()

    validate_required_files(errors)
    validate_paths(files, errors)
    validate_file_contents(files, errors)
    validate_safety_baseline(errors)
    validate_workflow_pinning(errors)

    if errors:
        print("Middleware repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Middleware repository validation passed for {len(files)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
