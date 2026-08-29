# Staging product authentication read matrix

## Goal

`scripts/staging_product_auth_read_matrix.py` proves the reviewed Keycloak → Kong → Middleware identity path without submitting a Middleware command and without reaching Odoo or any provider.

The harness uses only:

1. OAuth 2.0 Client Credentials token issuance for an explicitly selected staging service client; and
2. `GET /v1/operations/{command_id}` with a newly generated random UUID.

A valid product token is expected to receive `404` for that deliberately nonexistent operation. That result proves the original bearer survived Kong and was accepted by Middleware's caller/scope/tenant verification before the read reached the command ledger. The harness treats `200` as unexpected because the random operation is intended to be absent.

## Required source/runtime prerequisites

Do not run this harness until the reviewed source has been deployed to a staging environment:

- Keycloak contains the selected product service identities and their exact Middleware status scopes;
- Kong exposes the reviewed product `GET /v1/operations` route and preserves the original Authorization bearer;
- Middleware contains the reviewed original-caller policy;
- the staging command ledger is healthy enough to return normal authenticated read results;
- no-effect/live-write capability flags remain disabled.

The harness itself does not deploy or reconcile any of those components.

## Product matrix

The source policy must contain all six reviewed clients:

- `moneybee-backend`
- `breero-backend`
- `larim-a-backend`
- `transportation-backend`
- `beyvra-backend`
- `social-codestra`

Each token must satisfy:

- issuer `https://auth.codestra.co/realms/codestra`;
- audience `middleware-api`;
- `azp` equal to the selected product client;
- `exp > iat` and lifetime no greater than 300 seconds;
- the client's exact `*.middleware.status.read` scope;
- a non-empty, non-wildcard `tenant_id` claim.

The claim inspection inside the harness is only an evidence/preflight check. Kong and Middleware remain responsible for cryptographic verification and authorization.

## Per-client probes

For each selected product client the harness performs three GET probes against the same random operation UUID:

- **valid original bearer → 404**: authentication/authorization passed and the nonexistent read reached Middleware;
- **tampered JWT signature → 401**: the gateway/runtime rejects an invalidly signed bearer;
- **valid bearer + mismatched X-Tenant-ID → 403**: tenant isolation fails closed.

A separate request with no bearer must return `401`.

There are **zero** `POST /v1/commands` requests and zero provider calls.

## Secrets and environment

Set the environment marker and endpoints explicitly. The script has no default gateway or token endpoint so it cannot accidentally choose an environment:

```bash
export AUTH_MATRIX_ENVIRONMENT=staging
export AUTH_MATRIX_GATEWAY_BASE_URL='https://<reviewed-staging-gateway>'
export AUTH_MATRIX_TOKEN_ENDPOINT='https://<reviewed-keycloak>/realms/codestra/protocol/openid-connect/token'
```

Provide staging service-account secrets only through process environment variables. The convention is:

```text
AUTH_MATRIX_SECRET_MONEYBEE_BACKEND
AUTH_MATRIX_SECRET_BREERO_BACKEND
AUTH_MATRIX_SECRET_LARIM_A_BACKEND
AUTH_MATRIX_SECRET_TRANSPORTATION_BACKEND
AUTH_MATRIX_SECRET_BEYVRA_BACKEND
AUTH_MATRIX_SECRET_SOCIAL_CODESTRA
```

The repository contains no secret values. The harness does not print or write secrets or access tokens.

Run all six clients by default:

```bash
python3 scripts/staging_product_auth_read_matrix.py
```

Or select a reviewed subset:

```bash
AUTH_MATRIX_CLIENTS='moneybee-backend,social-codestra' \
  python3 scripts/staging_product_auth_read_matrix.py
```

## Evidence

Evidence defaults to a private directory under `/tmp/codestra-staging-auth-matrix-<UTC timestamp>`. Override with `AUTH_MATRIX_EVIDENCE_DIR` when an operator has prepared an approved evidence destination.

`auth-matrix-evidence.json` records:

- client IDs and required status scopes;
- issuer/audience/azp/lifetime facts;
- SHA-256 of the tenant ID instead of the tenant value itself;
- expected and actual HTTP status for each probe;
- only the structured error code when one exists;
- `command_posts: 0`, `provider_calls: 0`, `tokens_recorded: false`, and `secrets_recorded: false`.

The output must not be committed if local policy treats runtime identifiers/evidence as sensitive.

## Interpretation

A fully passing matrix is staging authentication evidence only. It does **not** authorize provider writes, Odoo writes, social publication, SMS/email delivery, dialing, crawling, provisioning, production route reconciliation, or production release.

If a valid read returns `401`, inspect Keycloak/Kong bearer preservation and client identity. If it returns `403`, inspect status scope and tenant claim/header agreement. If it returns `503`, repair Middleware/command-ledger readiness before treating the auth matrix as meaningful. Do not weaken authentication or tenant checks to make the matrix pass.
