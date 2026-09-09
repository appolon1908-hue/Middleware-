from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate_integration_fabric.py"


@pytest.mark.parametrize(
    "mutation", ["unknown_adapter", "non_boolean_capability", "direct_n8n"]
)
@pytest.mark.parametrize("optimized", [False, True])
def test_invalid_registry_fails_closed(
    tmp_path: Path, mutation: str, optimized: bool
) -> None:
    paths = [
        "config/system-ownership.v2.json",
        "config/capabilities.v2.json",
        "config/adapter-registry.v2.json",
        "contracts/platform/command-envelope.v1.schema.json",
        "connectors/generated/command-registry.v1.json",
        "contracts/platform/event-envelope.v1.schema.json",
        "contracts/event-envelope.schema.json",
        "contracts/platform/contract-catalog.v1.json",
    ]
    for path in paths:
        value = json.loads((ROOT / path).read_text())
        if (
            mutation == "unknown_adapter"
            and path == "connectors/generated/command-registry.v1.json"
        ):
            value["commands"][0]["connector_id"] = "missing-adapter"
        if (
            mutation == "non_boolean_capability"
            and path == "config/capabilities.v2.json"
        ):
            value["capabilities"]["UNBOUND_FLAG"] = ""
        if mutation == "direct_n8n" and path == "config/adapter-registry.v2.json":
            value["adapters"][0]["direct_n8n"] = True
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))
    source = (
        "import importlib.util,pathlib;"
        f'spec=importlib.util.spec_from_file_location("fabric",{str(SCRIPT)!r});'
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        f"m.ROOT=pathlib.Path({str(tmp_path)!r});m.validate()"
    )
    result = subprocess.run(
        [sys.executable, *(["-O"] if optimized else []), "-c", source],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "ValueError" in result.stderr or "AssertionError" in result.stderr


def test_committed_fabric_is_valid() -> None:
    spec = importlib.util.spec_from_file_location("fabric", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate()
