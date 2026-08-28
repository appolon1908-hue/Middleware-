# Redis Usage Map

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

The captured source defines these logical TTL namespaces in `app/core/realtime.py`; the implementation shown is an in-process bounded replay stand-in, and runtime configuration exposes Redis. No durable business truth may depend solely on these keys.

| NAMESPACE | CLASS | TTL_SECONDS | PURPOSE | DURABLE_TRUTH | TARGET |
|---|---|---:|---|---|---|
| `agent_presence` | session | 90 | agent presence | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |
| `active_call` | session | 7200 | active call | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |
| `call_agent` | session | 7200 | call agent | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |
| `call_campaign` | session | 7200 | call campaign | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |
| `websocket_route` | session | 90 | websocket route | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |
| `screen_pop_context` | temporary state | 900 | screen pop context | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |
| `rate_limit` | rate limit | 60 | rate limit | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |
| `distributed_lock` | lock | 30 | distributed lock | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |
| `appointment_preparation` | temporary state | 3600 | appointment preparation | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |
| `ai_conversation` | temporary state | 3600 | ai conversation | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |
| `partial_transcript` | temporary state | 900 | partial transcript | NO | namespaced by environment/tenant; PostgreSQL/event ledger remains authoritative |

Runtime Redis databases/queue names are configuration-driven (`REDIS_URL_FILE`, `QUEUE_NAME`) and do not disclose stable literal key prefixes in the captured source. The canonical implementation must declare exact prefixes before rollout; this is a design gap, not an unmapped server namespace.
