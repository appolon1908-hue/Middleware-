# Migration Waves

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

Each wave is gated by source provenance, default-deny capabilities, no-effect mocks, schema migration evidence, and independent PRs targeting `main`.

| WAVE | SCOPE | DEPENDS_ON | EXIT GATE |
|---|---|---|---|
| 0 Foundation | contracts; auth; tenant; capabilities; database; inbox/outbox; ledgers; NATS; Temporal; connector runtime | all later waves | unit + infrastructure + contract + failure/restart tests PASS |
| 1 Read-only | health; config; provider read-back; status; mappings | Wave 0 | unit + infrastructure + contract + failure/restart tests PASS |
| 2 Durable internal | scheduler; notifications; reconciliation; sync | Wave 0 | unit + infrastructure + contract + failure/restart tests PASS |
| 3 Odoo | results; lead sync; CRM commands | Waves 0-2 | unit + infrastructure + contract + failure/restart tests PASS |
| 4 n8n | workflow dispatch; result ingestion | Waves 0-2 | unit + infrastructure + contract + failure/restart tests PASS |
| 5 Communications | email; SMS; callbacks; receipts | Waves 0-2 | unit + infrastructure + contract + failure/restart tests PASS |
| 6 Social | Postiz/Postly boundary | Waves 0-2 | unit + infrastructure + contract + failure/restart tests PASS |
| 7 Telephony | VICIdial; PJSIP; webphone; provisioning orchestration | Waves 0-2 | unit + infrastructure + contract + failure/restart tests PASS |
| 8 Specialized | Kyqra; Breero; explicitly reviewed remainder | prior applicable waves | unit + infrastructure + contract + failure/restart tests PASS |
