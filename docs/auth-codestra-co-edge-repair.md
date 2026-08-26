# auth.codestra.co edge repair

## Ownership

This branch owns the public `auth.codestra.co` site behavior and acceptance criteria. Identity semantics remain owned by `integration/keycloak`; reverse-proxy implementation remains owned by `platform/caddy`; host execution and rollback remain owned by `operations/application-host`.

Booked4Seasons is explicitly out of scope.

## Required route

```text
Internet
  -> auth.codestra.co:443
  -> Caddy
  -> verified canonical Keycloak upstream
  -> realm: codestra
```

The edge must preserve:

```text
https://auth.codestra.co/realms/codestra
```

as the issuer exposed by OpenID Connect discovery.

## Pre-change gate

Do not reload Caddy until all are true:

- active Caddy process/container is identified;
- the exact loaded Caddy configuration source is identified;
- the current `auth.codestra.co` route and upstream are recorded;
- the canonical Keycloak upstream responds directly from Server A;
- the chosen route cannot recurse through public DNS back to Server A;
- complete active Caddy configuration validates;
- a timestamped backup and rollback command exist.

## Success criteria

```text
AUTH_PUBLIC_TLS=PASS
AUTH_CERTIFICATE_SAN=auth.codestra.co
AUTH_OPENID_DISCOVERY=HTTP_200
AUTH_ISSUER=https://auth.codestra.co/realms/codestra
AUTH_ACCOUNT_ROUTE=EXPECTED_KEYCLOAK_RESPONSE
AUTH_HTTP_502=ABSENT
CADDY_RELOAD=ZERO_DOWNTIME
UNRELATED_ROUTES=UNCHANGED
```

Also sample the other existing Caddy sites after reload to ensure this isolated repair did not alter their routing.

## Rollback trigger

Immediately restore the saved Caddy configuration and reload Caddy if any of these occurs:

- configuration validation fails;
- `auth.codestra.co` becomes unreachable;
- certificate validation fails;
- issuer changes from the canonical value;
- a proxy loop is observed;
- unrelated Caddy routes regress.

No Keycloak realm/client/user mutation is part of rollback because none is authorized by this edge repair.
