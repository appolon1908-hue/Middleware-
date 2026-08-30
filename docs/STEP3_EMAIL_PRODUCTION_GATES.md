# Step 3 Email Production Gates

Date: 2026-08-30

Step 3 is implementation-ready but not production-activated.

## Must Pass Before Production Sending

- Linux CI full suite, including shell syntax validation.
- Durable Communications read-model migration and rollback evidence.
- Keycloak to Kong to Middleware live auth matrix.
- Klyrow authenticated staging canary with safe-mode proof.
- SMTP/DNS/domain readiness evidence from Klyrow.
- Live Klyrow provider read-back canary; automated uncertain-outcome and
  duplicate-send prevention tests are now present in Middleware.
- Backup and restore evidence for communication state.
- Observability alerts for command failures, provider degradation, bounce/complaint spikes, and reconciliation backlog.
- Explicit approval to enable production delivery flags.

## Prohibited In This Branch

- No live Postal/Mautic sending.
- No production DNS activation.
- No Keycloak/Kong/Caddy deployment changes.
- No n8n or Odoo live side effects.
