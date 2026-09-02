# Rapid Domain + Campaign Onboarding

Purpose: make a new business/domain production-ready through one repeatable control-plane workflow while keeping Odoo, Middleware, n8n and VICIdial campaign state synchronized.

Canonical onboarding request fields: tenant_id, business_id, domain, environment, website_repository, website_release_sha, campaign_code, campaign_name, odoo_company_id, odoo_campaign_id, vicidial_campaign_id, inbound_group, timezone, locale, owner, capabilities, requested_routes, required_forms, communication_channels.

Canonical flow:

1. A new-domain manifest is committed and validated.
2. Caddy receives the approved hostname/TLS route.
3. Kong receives approved API routes and scopes only.
4. Keycloak identity/client/roles are provisioned where required.
5. Middleware registers the tenant/site/campaign binding.
6. Odoo campaign activation emits a durable campaign synchronization intent.
7. Middleware reconciles Odoo campaign state to VICIdial through the restricted adapter.
8. n8n receives orchestration events only after durable acceptance; it is not the authority.
9. Website forms/SDK calls carry tenant, campaign, correlation, consent, attribution and idempotency context.
10. Runtime read-back proves domain, campaign, routes, identities and release SHA before production activation.

Campaign synchronization must be idempotent and reconciliation-based. Odoo is business campaign authority; Middleware is synchronization/control-plane authority; VICIdial is telephony execution state. No direct Odoo-to-VICIdial database writes are permitted.

Required campaign sync states: requested, validating, provisioning, synchronized, degraded, reconciliation_required, suspended, retired.

Required synchronized assets where applicable: campaign identity/code, status, timezone, lead source mapping, inbound group, allowed agents/supervisors, dispositions, callbacks, recording policy, scripts, transfer targets, contact-center hours, DNC/consent policy, Odoo lead/activity mapping, communication templates, dashboards and n8n workflow bindings.

Unknown outcomes must be read back from VICIdial before retry. Duplicate Odoo events must not create duplicate campaigns.

External dialing/writes remain capability-gated and disabled until the individual campaign passes production activation checks.
