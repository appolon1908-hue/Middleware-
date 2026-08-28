# Odoo Integration Map

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

All effectful Odoo paths are classified `REPLACE_WITH_NEW_ARCHITECTURE` unless they already terminate in the canonical command/capability boundary. Direct writes are requirements evidence only.

| SOURCE_COMPONENT | TRIGGER | ODOO_MODEL | OPERATION | READ_OR_WRITE | TENANT_SCOPED | CAMPAIGN_SCOPED | IDEMPOTENT | READ_BACK | FAILURE_HANDLING | NEW_ARCH_OWNER | CLASSIFICATION |
|---|---|---|---|---|---|---|---|---|---|---|---|
| integration API | POST /api/v1/integrations/odoo/commands | configured Odoo model from command | command/read-back | WRITE | required | command/payload scoped | required by canonical ledger | required | retry + reconciliation | Odoo connector | REPLACE_WITH_NEW_ARCHITECTURE |
| odoo result worker | delivery/result event | CRM result/lead model | result delivery | WRITE | required | campaign/result scoped | server delivery key; canonical command key | required | outbox retry | Odoo connector worker | REPLACE_WITH_NEW_ARCHITECTURE |
| scraper Odoo delivery worker | validated scraper result | lead/customer | create/update | WRITE | required | required | required | required | review_pending then command | Kyqra/scraper + Odoo connectors | REPLACE_WITH_NEW_ARCHITECTURE |
| Breero Odoo worker | Breero lead/result | lead/customer | create/update | WRITE | required | required | required | required | retry/reconciliation | Breero + Odoo connectors | REPLACE_WITH_NEW_ARCHITECTURE |
| Odoo health/readiness | GET integration health/readiness | none | health/readiness | READ | service scoped | none | n/a | health probe | fail closed | Odoo connector | KEEP_AND_PORT |
