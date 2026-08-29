# Stage 4 Runtime Gate

Stage 4 can move toward production only when the six ordered gate steps in
`config/stage4-runtime-gate.v1.json` are all `PASS`. The gate is intentionally
source-controlled, reviewed, and fail-closed.

Current state:

- Original product bearer source and CI are green on the current main history.
- `auth.codestra.co` and `api.codestra.co` resolve from the verification
  environment.
- Keycloak OIDC discovery returns HTTP 200.
- Public `api.codestra.co` Middleware command/readiness routes still return 404
  from this environment.
- Staging migration lineage is still blocked by the unresolved
  `0053_callback_worker_grants` revision.

Run the source gate:

```bash
python3 scripts/verify_stage4_runtime_gate.py --allow-no-go
```

Run live probes from an approved verifier:

```bash
python3 scripts/verify_stage4_runtime_gate.py --allow-no-go --probe-live
```

Strict production mode must fail while the gate reports `NO_GO`:

```bash
python3 scripts/verify_stage4_runtime_gate.py
```

Do not activate production, enable provider delivery, import active n8n
workflows, run guessed Alembic repair commands, or mutate Odoo/SMS/email/call/
social/crawler state until this gate is `GO`.
