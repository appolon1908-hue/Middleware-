# Connector Matrix

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

Every external call must be owned by one connector. Timeout/retry values are contract parameters; no unbounded default survives migration.

| CONNECTOR | COMMANDS | EVENTS | AUTH | TIMEOUT | RETRY | IDEMPOTENCY | RATE_LIMIT | CIRCUIT_BREAKER | READ_BACK | CURRENT_SERVER_IMPLEMENTATION | TARGET_IMPLEMENTATION |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Odoo | customer/lead/result commands | result/read-back events | OAuth/service secret | bounded connect/read | ledger + Temporal | command key | tenant/provider quota | required | required | legacy API/workers | connector-runtime Odoo |
| n8n | workflow.dispatch | result/error/reconciliation | service JWT/HMAC | bounded | outbox | run/idempotency key | workflow quota | required | status callback | API + workers | n8n orchestration connector |
| VICIdial | call/control/read | call result/callback | OAuth2+mTLS | configured bounded | safe retry only | command key | provider limit | required | mandatory | vicidial_adapter | vicidial-restricted connector |
| Asterisk/PJSIP | extension/config commands | provision/status | mTLS/service auth | bounded | workflow retry | operation ID | provider limit | required | mandatory | pjsip_adapter | new PJSIP connector |
| Telnexa | communications commands | receipts | service credential | bounded | connector policy | command key | provider limit | required | receipt/status | flags only/evidence | connector-runtime manifest |
| Klyrow | communications commands | receipts | service credential | bounded | connector policy | command key | provider limit | required | receipt/status | flags only/evidence | connector-runtime manifest |
| Postiz/Postly | publish/cancel/media | results/analytics | provider credential | bounded | 429/5xx policy | operation key | provider limit | required | post status | routes + polling/social workers | social connector only |
| Kyqra/scraper | result intake | validated lead | signed webhook/service auth | bounded | inbox retry | source event key | ingress limit | required | review/read-back | scraper worker | Kyqra connector + normalization |
| Breero | lead/result intake | normalized lead | service credential | bounded | inbox retry | source event key | provider limit | required | source status | Breero worker | Breero connector |
| Provisioning service | desired-state command | operation status | OAuth2 service identity | bounded | Temporal/reconciliation | request + operation ID | service quota | required | mandatory | extension allocator/telephony provisioning | provisioning connector |
