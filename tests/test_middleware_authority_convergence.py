from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "config" / "middleware-authority-convergence.v1.json"
VALIDATOR = ROOT / "scripts" / "validate_middleware_authority_convergence.py"

spec = importlib.util.spec_from_file_location("middleware_authority_validator", VALIDATOR)
assert spec is not None and spec.loader is not None
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def _document() -> dict[str, object]:
    value = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_reviewed_authority_convergence_record_is_fail_closed() -> None:
    assert validator.validate_document(_document(), root=ROOT) == []


def test_legacy_family_cannot_become_forward_authority() -> None:
    value = copy.deepcopy(_document())
    family = value["runtimeImageFamilies"][1]
    family["role"] = "forward"
    errors = validator.validate_document(value, root=ROOT)
    assert any("legacy family must be rollback-only" in error for error in errors)


def test_candidate_reference_must_bind_exact_digest() -> None:
    value = copy.deepcopy(_document())
    candidate = value["forwardAuthority"]["image"]["currentSignedCandidate"]
    candidate["imageReference"] = (
        "ghcr.io/appolon1908-hue/codestra-middleware@"
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )
    errors = validator.validate_document(value, root=ROOT)
    assert any("candidate image reference" in error for error in errors)


def test_workload_cannot_appear_in_multiple_image_families() -> None:
    value = copy.deepcopy(_document())
    duplicate = value["runtimeImageFamilies"][0]["workloads"][0]
    value["runtimeImageFamilies"][1]["workloads"].append(duplicate)
    value["serverA"]["runtimeWorkloadsCatalogued"] += 1
    errors = validator.validate_document(value, root=ROOT)
    assert any("workload appears in multiple image families" in error for error in errors)


def test_server_a_mutation_cannot_be_claimed_by_repository_metadata() -> None:
    value = copy.deepcopy(_document())
    value["serverA"]["runtimeMutationStatus"] = "PASS"
    value["serverA"]["productionChanged"] = True
    errors = validator.validate_document(value, root=ROOT)
    assert any("must not claim a Server A mutation" in error for error in errors)
    assert any("productionChanged must be false" in error for error in errors)
