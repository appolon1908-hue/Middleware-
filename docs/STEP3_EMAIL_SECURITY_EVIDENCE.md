# Step 3 Email Security Evidence

Date: 2026-08-29

## Implemented Controls

- Every create/read/cancel path requires bearer verification through the existing runtime token verifier.
- Product caller identity is resolved from the original bearer token model.
- Email send authorization uses the command policy registry for `email.message.send.v1` and target `klyrow-email`.
- Tenant authorization is enforced against `X-Tenant-ID`.
- Actor identity must match the verified token subject when submitting a message.
- Correlation and idempotency headers are required before creating effects.
- Consent and suppression checks run before provider command submission.
- Signed Klyrow webhook ingress updates the canonical read model without adding live provider write access.

## Production Security Gates Still Required

- Live Keycloak issuer, audience, scope, and caller tests through Kong.
- Secrets from an external secret store.
- Durable event replay protection for canonical communications events.
- Live negative auth matrix: no token, invalid token, wrong scope, wrong caller, wrong tenant.
