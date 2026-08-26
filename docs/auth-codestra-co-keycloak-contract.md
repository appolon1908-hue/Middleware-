# auth.codestra.co Keycloak repair contract

## Scope

This workstream owns the identity-side contract for repairing `auth.codestra.co` without changing Keycloak realm data, users, credentials, TOTP, clients, Odoo, n8n, telephony, or Booked4Seasons.

Canonical identity contract:

```text
issuer=https://auth.codestra.co/realms/codestra
realm=codestra
openid_configuration=/realms/codestra/.well-known/openid-configuration
```

The edge repair must preserve that issuer exactly. Applications must not be redirected back to `auth.codestra.agency` or another hostname.

## Current repair hypothesis

The observed public symptom is HTTP `502` at `auth.codestra.co`. A `502` is an edge/upstream failure and must not be treated as authorization to modify Keycloak realm state.

Historical/current operational evidence identifies `49.12.145.107` as the canonical Keycloak runtime host. That address is a discovery input, not automatic deployment authority. Server A must verify the actual reachable Keycloak endpoint before any Caddy route is changed.

## Required discovery evidence

Before an edge change, prove all of the following from the Caddy host:

```text
CANONICAL_ISSUER=https://auth.codestra.co/realms/codestra
UPSTREAM_RUNTIME_IDENTIFIED=PASS
UPSTREAM_TCP_REACHABLE=PASS
UPSTREAM_TLS_OR_HTTP_MODE_IDENTIFIED=PASS
OPENID_CONFIGURATION_DIRECT_UPSTREAM=HTTP_200
ACTIVE_CADDY_ROUTE_IDENTIFIED=PASS
PROXY_LOOP_ABSENT=PASS
```

If the verified upstream is remote HTTPS, TLS verification must use the canonical server name `auth.codestra.co`. If the verified upstream is a local/private Keycloak service, the Caddy workstream must use that exact private service endpoint instead. Do not guess between these models.

## Acceptance

After the edge repair, require:

```text
GET https://auth.codestra.co/realms/codestra/.well-known/openid-configuration = 200
issuer field = https://auth.codestra.co/realms/codestra
GET https://auth.codestra.co/realms/codestra/account/ = expected Keycloak response/redirect
certificate SAN includes auth.codestra.co
public certificate chain validates
HTTP 502 absent
```

The repair is incomplete if the public route returns 200 but the discovery document advertises a different issuer.

## Forbidden actions

- Do not create, delete, or modify users, realms, clients, roles, credentials, or TOTP.
- Do not expose Keycloak admin endpoints or credentials.
- Do not make Caddy proxy `auth.codestra.co` back to `auth.codestra.co` through public DNS; that can create a proxy loop.
- Do not disable upstream certificate verification to make a broken route appear healthy.
- Do not change Booked4Seasons as part of this repair.
