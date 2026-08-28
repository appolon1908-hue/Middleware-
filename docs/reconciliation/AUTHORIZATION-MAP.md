# Authentication and Authorization Map

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

Browser-supplied tenant, role, or campaign and unverified gateway headers are prohibited migration inputs. Canonical authorization is default-deny and derives tenant/campaign from verified identity plus server-side grants.

| PATH/BOUNDARY | CURRENT AUTH | KEYCLOAK/JWT | TENANT MODEL | ACTION |
|---|---|---|---|---|
| global /api and /v1 guard | shared bearer secret | no | header/payload conventions | REPLACE with OIDC service/user validation and canonical tenant context |
| signed webhook paths | HMAC/signature helpers | partial | payload-derived | KEEP behavior; use raw-body HMAC, timestamp, replay and tenant route binding |
| /webphone-api/v1 | route-specific Keycloak/JWT | yes in handler | claims + request | KEEP_AND_PORT; isolate session issuance from call authority |
| VICIdial adapter | OAuth2/mTLS files | service | command context | KEEP_AND_PORT into restricted connector |
| publisher/canary | publisher auth + nonce/ack tables | publisher scope | payload/claim | REPLACE with canonical signed activation/capability |
| gateway trust headers | not globally verified | no | possible header trust | UNSAFE: never trust tenant/role/campaign without cryptographic gateway contract |
