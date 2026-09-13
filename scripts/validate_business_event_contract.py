#!/usr/bin/env python3
"""Generate/check the normalized inbox contract from its actual private router."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from fastapi import FastAPI
    from app.api.internal.business_events import router
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    app = FastAPI(title="Codestra normalized business event ingress", version="1.0.0")
    app.include_router(router)
    schema = app.openapi()
    schema["components"]["securitySchemes"] = {"serviceBearer": {
        "type": "http", "scheme": "bearer", "bearerFormat": "JWT",
        "description": "Keycloak klyrow-business-events workload; klyrow.events.write scope and tenant-bound claims.",
    }}
    operation = schema["paths"]["/internal/v1/events/klyrow"]["post"]
    operation["security"] = [{"serviceBearer": []}]
    operation["parameters"] = [p for p in operation["parameters"] if p["name"].lower() != "authorization"]
    for parameter in operation["parameters"]:
        # Handler additionally binds these headers to the body; absence is 409.
        parameter["required"] = True
    expected = json.dumps(schema, indent=2, sort_keys=True)+"\n"
    path = ROOT/"contracts/business-events.internal.openapi.json"
    if args.write:
        path.write_text(expected)
    elif path.read_text() != expected:
        raise SystemExit("business_event_contract_drift")
    print("BUSINESS_EVENT_RUNTIME_CONTRACT=PASS")


if __name__ == "__main__":
    main()
