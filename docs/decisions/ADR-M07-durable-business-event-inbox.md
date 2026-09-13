# Normalized Klyrow business event inbox

The mission envelope coexists with existing provider-event protocols. Accept it
only at `/internal/v1/events/klyrow` in the private integration application.
The Keycloak workload must have authorized party `klyrow-business-events`, the
configured audience/issuer/environment and `klyrow.events.write`. Cross-tenant
aggregation additionally requires `klyrow.events.write:any-tenant`; otherwise
the token tenant must equal the event tenant. Deploy behind the private mTLS
listener. Do not expose the route through public Kong routes.

Migration `0061_codestra_business_events` adds a durable inbox keyed by source,
tenant and event ID. A savepoint handles concurrent insertion races; a changed
payload under the same identity is a conflict. The transaction commits before
the API returns 202. Invalid JSON, wrong tenant, missing header binding and
storage errors cannot acknowledge a fact. The request body is bounded to 64 KiB.

Daily usage facts contain replacement totals, ordered by `snapshot_at`, never
financial debit commands. This patch stores accepted facts as PENDING. It does
not yet map these new facts onto existing Odoo KPI models. The Odoo projector
must be implemented and verified against those models before business sync can
be certified; a 202 inbox response is not an Odoo completion response.

Deploy the migration and receiver before enabling Klyrow's optional publisher.
Verify duplicate replay and conflict behavior privately, then render the
service JWT and TLS credentials through OpenBao. No Odoo credential is shared
with Klyrow or observability services.

Rollback: stop the publisher first and retain accepted inbox rows. The migration
deliberately refuses an automatic destructive downgrade. The old event and
Alertmanager routes remain available throughout migration.

Validation: authenticated HTTP acceptance/replay/tenant tests, plus concurrent
replay against a disposable PostgreSQL database with the real migration SQL.
`scripts/validate_business_event_contract.py` checks the generated route contract
in CI. Live Odoo and network-policy acceptance remain outstanding.

The PR advances the required schema head and migration-history hash together
with the new migration. Runtime metadata, validators and synthetic fixtures
use that same head. The protected release candidate remains pending with no
current signed candidate or promotion authorization. Historical signed evidence
is retained as historical evidence; it does not certify this migration.
