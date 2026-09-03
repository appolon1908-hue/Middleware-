#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    value = path.read_text(encoding="utf-8")
    if value.count(old) != 1:
        raise SystemExit(f"{path}: expected one replacement for {old[:80]!r}")
    path.write_text(value.replace(old, new), encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_pr107_matrix_fix.py TARGET_ROOT")
    root = Path(sys.argv[1]).resolve()
    script = root / "scripts/staging_product_auth_read_matrix.py"
    docs = root / "docs/STAGING-PRODUCT-AUTH-READ-MATRIX.md"
    tests = root / "tests/test_staging_product_auth_read_matrix.py"

    replace_once(
        script,
        '''        is_provider = client_id in provider_scopes
        if is_provider:
            if status_scope not in provider_scopes[client_id]:
                raise MatrixError(
                    f"{client_id}: read probe scope is not bound to its provider operation"
                )
            if raw.get("connector_commands_allowed") is not False:
''',
        '''        is_provider = client_id in provider_scopes
        if is_provider:
            if not status_scope.endswith(".denied"):
                raise MatrixError(
                    f"{client_id}: generic operation read scope is not fail-closed"
                )
            probe_scope = sorted(provider_scopes[client_id])[0]
            if raw.get("connector_commands_allowed") is not False:
''',
    )
    replace_once(
        script,
        '''        clients[client_id] = MatrixClient(
            client_id=client_id,
            status_scope=status_scope,
            secret_environment=_secret_environment(client_id),
            provider_control=is_provider,
        )
''',
        '''        clients[client_id] = MatrixClient(
            client_id=client_id,
            status_scope=probe_scope if is_provider else status_scope,
            secret_environment=_secret_environment(client_id),
            provider_control=is_provider,
        )
''',
    )
    replace_once(
        script,
        '''    forwarded_authorization: str | None = None,
) -> httpx.Response:
''',
        '''    forwarded_authorization: str | None = None,
    provider_control: bool = False,
) -> httpx.Response:
''',
    )
    replace_once(
        script,
        '''    return client.request(
        method="GET",
        url=f"{gateway_base_url}/v1/operations/{operation_id}",
        headers=headers,
    )
''',
        '''    route = (
        f"/api/v1/control/identity-probes/{operation_id}"
        if provider_control
        else f"/v1/operations/{operation_id}"
    )
    return client.request(
        method="GET",
        url=gateway_base_url + route,
        headers=headers,
    )
''',
    )
    replace_once(
        script,
        '''                        authorization=f"Bearer {token}",
                        tenant_id=tenant_id,
                    ),
''',
        '''                        authorization=f"Bearer {token}",
                        tenant_id=tenant_id,
                        provider_control=matrix_client.provider_control,
                    ),
''',
    )
    replace_once(
        script,
        '''                        authorization=f"Bearer {tamper_signature(token)}",
                        tenant_id=tenant_id,
                    ),
''',
        '''                        authorization=f"Bearer {tamper_signature(token)}",
                        tenant_id=tenant_id,
                        provider_control=matrix_client.provider_control,
                    ),
''',
    )
    replace_once(
        script,
        '''                        authorization=f"Bearer {token}",
                        tenant_id="matrix-mismatch-" + uuid.uuid4().hex,
                    ),
''',
        '''                        authorization=f"Bearer {token}",
                        tenant_id="matrix-mismatch-" + uuid.uuid4().hex,
                        provider_control=matrix_client.provider_control,
                    ),
''',
    )
    replace_once(
        script,
        '''        for case, fixture in sorted(fixtures.items()):
            records.append(
''',
        '''        for case, fixture in sorted(fixtures.items()):
            fixture_claims = decode_unverified_claims(fixture["token"])
            fixture_client = policy_clients.get(str(fixture_claims.get("azp", "")))
            records.append(
''',
    )
    replace_once(
        script,
        '''                        authorization=f"Bearer {fixture['token']}",
                        tenant_id=fixture["tenant_id"],
                    ),
''',
        '''                        authorization=f"Bearer {fixture['token']}",
                        tenant_id=fixture["tenant_id"],
                        provider_control=(
                            fixture_client.provider_control
                            if fixture_client is not None
                            else False
                        ),
                    ),
''',
    )
    replace_once(
        script,
        '''        "route": "/v1/operations/{command_id}",
''',
        '''        "routes": {
            "generic_operation": "/v1/operations/{command_id}",
            "provider_identity": "/api/v1/control/identity-probes/{probe_id}",
        },
''',
    )

    replace_once(
        docs,
        '''The harness performs only two network operation classes:

1. OAuth 2.0 Client Credentials token issuance at the explicitly supplied staging token endpoint.
2. `GET /v1/operations/{command_id}` using a freshly generated random UUID.

A valid bearer must receive tenant-scoped `404` for that deliberately nonexistent operation. That result proves that the original token passed cryptographic verification, exact issuer/audience/`azp`/scope checks, and tenant authorization before the read reached the durable command ledger.
''',
        '''The harness performs only two network operation classes:

1. OAuth 2.0 Client Credentials token issuance at the explicitly supplied staging token endpoint.
2. One no-effect authenticated `GET` using a freshly generated random UUID:
   - ordinary product and automation callers use `/v1/operations/{command_id}`;
   - provider-control callers use `/api/v1/control/identity-probes/{probe_id}` so their deliberately denied generic operation-read scope remains fail closed.

A valid bearer must receive tenant-scoped `404` for that deliberately nonexistent resource. That result proves that the original token passed cryptographic verification, exact issuer/audience/`azp`/scope checks, and tenant authorization. The provider identity probe does not access the command ledger or any provider adapter.
''',
    )
    replace_once(
        docs,
        '''Provider-control callers are registered as read-only in the generic operation plane:

- their generic mutation scope ends in `.denied` and is not granted;
- `connector_commands_allowed=false`;
- `allowed_command_prefixes=[]`;
- `allowed_targets=[]`;
- their GET probe uses one exact provider-operation scope already present in the canonical identity grant.
''',
        '''Provider-control callers remain denied in the generic operation plane:

- their generic read and mutation scopes end in `.denied` and are not granted;
- `connector_commands_allowed=false`;
- `allowed_command_prefixes=[]`;
- `allowed_targets=[]`;
- their no-data identity probe uses one exact provider-operation scope already present in the canonical identity grant.
''',
    )
    replace_once(docs, "- the configured status/read probe scope is present;\n", "- the exact selected read/probe scope is present;\n")
    replace_once(docs, "- client ID and required scope;\n", "- client ID, required scope, and selected no-effect probe class;\n")

    test_block = '''\n\ndef test_provider_callers_use_the_no_data_identity_probe() -> None:\n    module = load_module()\n    clients = module._load_policy()\n    provider = clients["codestra-ai"]\n    ordinary = clients["moneybee-backend"]\n    assert provider.provider_control is True\n    assert provider.status_scope == "ai.inference.request"\n    assert ordinary.provider_control is False\n    assert ordinary.status_scope == "moneybee.middleware.status.read"\n\n    requests = []\n\n    def respond(request):\n        requests.append(request)\n        return module.httpx.Response(404, request=request)\n\n    transport = module.httpx.MockTransport(respond)\n    with module.httpx.Client(transport=transport) as client:\n        module._operation_get(\n            client,\n            gateway_base_url="https://gateway.test.invalid",\n            operation_id=module.uuid.uuid4(),\n            authorization="Bearer ordinary",\n            tenant_id="tenant-test",\n        )\n        module._operation_get(\n            client,\n            gateway_base_url="https://gateway.test.invalid",\n            operation_id=module.uuid.uuid4(),\n            authorization="Bearer provider",\n            tenant_id="tenant-test",\n            provider_control=True,\n        )\n\n    assert requests[0].url.path.startswith("/v1/operations/")\n    assert requests[1].url.path.startswith("/api/v1/control/identity-probes/")\n'''
    replace_once(
        tests,
        "def test_provider_callers_cannot_use_generic_mutation_authority() -> None:\n",
        test_block + "\n\ndef test_provider_callers_cannot_use_generic_mutation_authority() -> None:\n",
    )
    replace_once(
        tests,
        '''        assert caller["connector_commands_allowed"] is False
''',
        '''        assert caller["status_scope"].endswith(".denied")
        assert caller["connector_commands_allowed"] is False
''',
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
