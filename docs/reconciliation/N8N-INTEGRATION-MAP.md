# n8n Integration Map

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

n8n may orchestrate workflows but is not a cross-system write authority. Any workflow credential that can mutate protected systems directly is unsafe and must be replaced by a Middleware command.

| WORKFLOW_TRIGGER | MIDDLEWARE_ENDPOINT | EVENT | PAYLOAD | AUTHENTICATION | TENANT | CAMPAIGN | WRITE_AUTHORITY | CALLBACK | RETRY | DUPLICATE_HANDLING |
|---|---|---|---|---|---|---|---|---|---|---|
| runtime dispatch | POST /api/v1/integrations/n8n/dispatch | command event | canonical envelope | service auth/shared bearer | required | required | Middleware only | results/errors/reconciliation endpoints | outbox/Temporal | ledger duplicate key |
| result ingestion | POST results/errors/reconciliation | result event | schema registry envelope | service auth | required | required | Middleware validation | command completion | durable inbox | event key |
| staging compatibility | /v1/n8n/* | calls/transcription/follow-up/QA | legacy schemas | legacy guard varies | required | required | must be removed from n8n | callbacks/jobs | legacy | legacy job/run IDs |
| social delivery worker | worker event | social publish command | Postiz/Postly mapping | service credential | required | required | Middleware capability | provider result | connector retry | operation key |
