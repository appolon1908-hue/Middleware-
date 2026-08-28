# Observability Map

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

Every canonical runtime requires liveness, readiness, metrics, structured logs, audit, and correlation. Liveness must not assert dependency health; readiness must fail closed for required dependencies.

| RUNTIME | LIVENESS | READINESS | METRICS | STRUCTURED_LOGS | AUDIT | CORRELATION |
|---|---|---|---|---|---|---|
| API | /healthz,/readyz,/metrics | dependency readiness | HTTP/request/command metrics | JSON logs | security+command audit | X-Correlation-ID |
| workers | runtime factory health/readiness/dependencies | DB/provider readiness | poll/lease/retry/dead-letter | JSON logs | worker action audit | correlation/command ID |
| connector runtime | health/readiness + management | DB/manifest/secret readiness | operations/webhooks/outbox | JSON logs | connector audit_log | operation/event ID |
| adapters | health/readiness | provider auth/network readiness | latency/retry/circuit | JSON logs | effect/read-back audit | command ID |
| PostgreSQL/Redis | container health | migration/ACL readiness | pool/latency/storage | platform logs | migration evidence | release ID |
