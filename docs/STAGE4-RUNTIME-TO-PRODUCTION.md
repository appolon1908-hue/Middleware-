# Stage 4 Runtime Gate to Production

This repository must not move Stage 4 n8n orchestration into production from
branch names, chat status, or source-only tests. Production remains blocked
until the ordered runtime gate in `config/stage4-runtime-gate.v1.json` is
changed by reviewed evidence and the validator reports `STAGE4_RUNTIME_GATE=GO`.

## Required order

1. Middleware original-bearer PR and exact-head CI pass.
2. Staging Middleware Alembic lineage is repaired, including the missing
   `0053_callback_worker_grants` ancestry problem.
3. `auth.codestra.co` and `api.codestra.co` resolve and the OIDC/API paths are
   reachable from the staging execution environment.
4. The live Keycloak -> Kong -> Middleware authorization matrix passes.
5. CP-ODOO runs through staging n8n to Middleware with all delivery flags off,
   producing the expected staging result and zero unexpected DLQ entries.
6. A production release manifest binds source SHA, image digest, workflow export
   hashes, backup/restore proof, rollback proof, and independent approval.

Run the source gate in CI:

```bash
python scripts/verify_stage4_runtime_gate.py --allow-no-go
```

Run live reachability only from an approved staging verifier:

```bash
python scripts/verify_stage4_runtime_gate.py --allow-no-go --probe-live
```

Do not edit production containers, enable provider delivery, apply Keycloak,
activate Kong routes, import active n8n workflows, or turn on Odoo/email/SMS/
telephony/social/crawler writes until the gate is `GO`.
