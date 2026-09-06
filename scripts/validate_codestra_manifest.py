#!/usr/bin/env python3
"""Fail closed when the canonical Codestra service manifest is incomplete."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", type=Path, default=Path(".codestra/service.yaml"))
    parser.add_argument("--schema", type=Path, default=Path("contracts/platform/service.v1.schema.json"))
    args = parser.parse_args()
    document = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document), key=lambda item: list(item.path))
    if errors:
        for error in errors:
            location = ".".join(str(part) for part in error.absolute_path) or "$"
            print(f"{location}: {error.message}")
        return 1
    print(f"MANIFEST_VALID=PASS service={document['metadata']['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
