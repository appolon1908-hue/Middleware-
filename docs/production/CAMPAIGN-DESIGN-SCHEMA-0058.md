# Campaign design schema release proposal

This dependency change advances the required source schema from
`0057_platform_service_catalog` to `0058_campaign_design`. It adds immutable
campaign design revisions, current revision pointers, resource reservations,
idempotent event receipts, retry records, and audited approvals.

No database has been migrated by this source change. The existing signed release
observations retain their actual `0057_platform_service_catalog` schema; they do
not attest this candidate. The new signed candidate remains pending and no
production or external-effect authority is granted.

The application integration belongs in the dependent campaign design PR. Review
this schema and forward release tuple separately before merging that integration.
The previous immutable migration history is retained byte for byte, with the new
migration appended and the history digest recomputed from those source bytes.

Validation: the new tables were installed into an isolated PostgreSQL 17 schema.
The dependent integration tests exercised concurrent event replay and allocation,
revision changes, approval scope and idempotency, and rollback after injected
failure. The production database remains unchanged.

Release gates remain required: protected review, exact-main signed image and
schema evidence, backup and isolated restore, rollback rehearsal, and production
read-back. Adding tables does not authorize campaign provisioning or activation.
