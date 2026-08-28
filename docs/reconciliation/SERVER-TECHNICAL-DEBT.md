# Server Technical Debt

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

These defects are not architecture requirements and must not be copied as part of functional migration.

| DEFECT | DOMAIN | EVIDENCE | DISPOSITION |
|---|---|---|---|
| obsolete OpenSSL 3.5.7-r0 test-image pin | build reproducibility | captured target fails against Alpine package 3.5.8-r0 | fix constraint/base set in next PR; rebuild actual target |
| 20 Ruff findings | quality | captured static scan | classify and fix; no blanket ignore |
| 9 mypy errors | type safety | captured static scan | fix model boundaries; local documented suppressions only |
| mixed runtime revisions | release integrity | 32 containers / 16 image IDs | one release manifest/source SHA |
| dirty operational checkout | provenance | server source manifest | build only from clean CI checkout |
| 26-input Compose overlay chain | deployment drift | captured Compose labels/index | four canonical environments |
| unknown OCI revision | supply chain | social image revision unknown and upstream labels blank | block app release until all images labeled |
| legacy shared bearer and payload tenant conventions | security | captured main.py/routes | OIDC/HMAC and verified tenant context |
| parallel server queue/schema families | durability | integration_* and event_inbox/outbox_event coexist | schema migration and one durable authority |
