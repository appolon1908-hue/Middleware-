#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts/moneybee-account-provisioned.schema.json").read_text())
ROUTING = json.loads((ROOT / "config/moneybee-account-event-routing.json").read_text())

assert SCHEMA["properties"]["event_type"]["const"] == "moneybee.account.provisioned.v1"
assert SCHEMA["properties"]["actor"]["properties"]["issuer"]["const"] == "https://auth.codestra.co/realms/codestra"
data = SCHEMA["properties"]["data"]
assert data["additionalProperties"] is False
assert data["properties"]["email_verified"]["const"] is True
assert data["properties"]["membership_type"]["const"] == "BORROWER"

assert ROUTING["eventType"] == "moneybee.account.provisioned.v1"
assert ROUTING["authoritativeBoundaries"]["humanIdentityAuthority"] == "keycloak"
assert ROUTING["authoritativeBoundaries"]["crossSystemMutationBoundary"] == "middleware"
assert ROUTING["marketing"]["securityEmailPath"] == "prohibited"
assert ROUTING["marketing"]["mauticSynchronousIdentityMail"] is False

prohibited = set(ROUTING["prohibitedPayloadFields"])
required_prohibited = {
    "password",
    "verification_code",
    "otp",
    "reset_token",
    "access_token",
    "refresh_token",
    "smtp_password",
}
assert required_prohibited <= prohibited
assert prohibited.isdisjoint(data["properties"].keys())

routes = {route["destination"]: route for route in ROUTING["routes"]}
assert set(routes) == {"odoo-integration", "n8n-automation"}
assert routes["odoo-integration"]["command"] == "crm.contact.upsert.v1"
assert routes["n8n-automation"]["command"] == "onboarding.started.v1"
assert all(route["delivery"] == "transactional-outbox" for route in routes.values())

print("MONEYBEE_ACCOUNT_EVENT_CONTRACT=PASS")
