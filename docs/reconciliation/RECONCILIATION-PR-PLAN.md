# Reconciliation PR Plan

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

Every branch below is created independently from then-current `main`; every PR targets `main`. There are no feature-to-feature PR chains.

| PR | BRANCH | SCOPE | REQUIRED GATE |
|---:|---|---|---|
| 1 | fix/runtime-docker-reproducibility | OpenSSL/base/package reproducibility | container build + secret scan |
| 2 | fix/runtime-quality | Ruff/mypy canonical runtime cleanup | Ruff PASS; mypy PASS |
| 3 | feat/runtime-endpoint-compatibility | selected endpoint contracts and auth boundary | route/tenant/idempotency tests |
| 4 | feat/runtime-worker-consolidation | scheduler/notification/sync/reconciliation | restart/redelivery tests |
| 5 | feat/runtime-odoo-connector | Odoo command/read-back | mock + capability tests |
| 6 | feat/runtime-n8n-connector | n8n orchestration boundary | mock + forbidden-direct-write tests |
| 7 | feat/runtime-communications-connectors | SMS/email/callback/receipts | provider mocks; effects disabled |
| 8 | feat/runtime-social-connector | Postiz/Postly | social mocks |
| 9 | feat/runtime-telephony-connectors | VICIdial/PJSIP/webphone/provisioning boundary | telephony mocks |
| 10 | feat/runtime-specialized-connectors | Kyqra/Breero reviewed flows | review/dedupe/Odoo mock |
| 11 | fix/runtime-database-reconciliation | schema/backfill/migration locks | empty/previous/downgrade/upgrade |
| 12 | fix/runtime-compose-consolidation | four environment compositions | compose config + provenance |
| 13 | test/runtime-distributed-e2e | full durable chain and failure matrix | distributed E2E PASS |
