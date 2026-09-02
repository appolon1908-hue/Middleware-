import json,yaml
from app.main import create_app

METHODS={"get","post","put","patch","delete"}
def _routes(paths): return {(method.upper(),path) for path,item in paths.items() for method in item if method in METHODS}

def test_generated_openapi_contract_and_matrix_match_runtime(test_settings):
    runtime=create_app(settings=test_settings).openapi()
    generated=json.load(open("contracts/platform/middleware-openapi.generated.json",encoding="utf-8"))
    contract=yaml.safe_load(open("contracts/platform/integration-fabric-api.v2.yaml",encoding="utf-8"))
    matrix=yaml.safe_load(open("config/api-completion-matrix.yaml",encoding="utf-8"))
    expected=_routes(runtime["paths"])
    assert expected==_routes(generated["paths"])==_routes(contract["paths"])
    assert expected=={(row["method"],row["path"]) for row in matrix["operations"]}
    assert matrix["classification_complete"] is True and matrix["unknown_endpoints"]==0
    assert not {"MISSING","PARTIAL","UNKNOWN"}&{row["runtime_state"] for row in matrix["operations"]}
    assert generated["components"]["securitySchemes"]["bearerAuth"]["scheme"]=="bearer"

def test_generated_contract_documents_mutation_headers():
    contract=yaml.safe_load(open("contracts/platform/integration-fabric-api.v2.yaml",encoding="utf-8"))
    for path,method in (("/v1/inbox/{record_id}/quarantine","post"),("/v1/outbox/{record_id}/cancel","post"),("/v1/operations/{command_id}/cancel","post")):
        names={item["name"] for item in contract["paths"][path][method]["parameters"]}
        assert {"X-Tenant-ID","X-Correlation-ID","Idempotency-Key"}<=names
