# Codestra Complete System Integration Map

## Binding state

```text
MIDDLEWARE_ONLY_CROSS_SYSTEM_WRITE_AUTHORITY=YES
REPOSITORY_COUNT=54
DEFAULT_POLICY=DENY
DIRECT_N8N_PROVIDER_ACCESS=NO
LIVE_EFFECTS_ENABLED=NO
DEPLOYMENT_STATE=DISABLED
PRODUCTION_STATE=NO_GO
```

`appolon1908-hue/Middleware-` owns the cross-system command, event, idempotency, inbox/outbox, operation, audit, capability, read-back, and reconciliation boundary. Every other repository retains its principal runtime or application authority.

## Canonical flow

```text
Browser / product backend / service
              |
              v
            Caddy
              |
              v
             Kong <---- Keycloak issuer/JWKS/roles
              |
              v
          Middleware
      +-------+--------+---------+---------+
      |       |        |         |         |
      v       v        v         v         v
    Odoo   Klyrow   Telnexa   VICIdial   Kyqra
             |        |          |         |
             +--------+----------+---------+
                          | signed/private events
                          v
                     Middleware inbox
                          |
                 NATS / Temporal / n8n
                          |
                    read models / SDK
```

n8n calls only the private Middleware automation API. Provider callbacks terminate at Middleware. Unknown external outcomes are reconciled before any resubmission.

## Complete repository matrix

| # | System | Principal repository | Cell | Integration mode | Source state |
|---:|---|---|---|---|---|
| 1 | `frontend-restaurant` | `appolon1908-hue/Frontend-Resturant-` | `product-clients` | public intake/client | partial |
| 2 | `codestra-production-platform` | `appolon1908-hue/codestra-production-platform` | `governance` | reference only | evidence only |
| 3 | `codestraxxxx` | `appolon1908-hue/Codestraxxxx` | `legacy-disabled` | disabled | unclassified |
| 4 | `codestra-frontend` | `appolon1908-hue/codestra` | `product-clients` | public intake/client | partial |
| 5 | `beyvra-backend` | `appolon1908-hue/beyvra-backend` | `financial-isolated` | nonfinancial adapter/client | contract defined |
| 6 | `codestra-backend` | `appolon1908-hue/codestra-backend` | `product-clients` | product caller | canonical decision required |
| 7 | `codestra-cms-backend` | `appolon1908-hue/backend2` | `product-clients` | product caller | canonical decision required |
| 8 | `beyvra-frontend` | `appolon1908-hue/beyvra-frontend` | `financial-isolated` | frontend/client | partial |
| 9 | `scrapper-legacy` | `appolon1908-hue/scrapper` | `legacy-disabled` | disabled | legacy |
| 10 | `breero` | `appolon1908-hue/Breero.com` | `product-clients` | product caller | partial |
| 11 | `booked4seasons` | `appolon1908-hue/booked4seasons` | `product-clients` | public intake | partial |
| 12 | `kyqra-legacy` | `appolon1908-hue/kyqra` | `legacy-disabled` | disabled | legacy |
| 13 | `telnexa-sms` | `appolon1908-hue/telnexa` | `communications` | SMS adapter/event source | source partial |
| 14 | `kyqra-crawler` | `appolon1908-hue/kyqra-crawler` | `crawler` | crawler adapter/event source | contract defined |
| 15 | `klyrow-email` | `appolon1908-hue/klyrow.com` | `communications` | email adapter/event source | source partial |
| 16 | `provisioning` | `appolon1908-hue/codestra-provisioning-service` | `core-control-plane` | provisioning adapter/event source | contract defined |
| 17 | `moneybee-frontend` | `appolon1908-hue/Moneybee-frontend-` | `product-clients` | frontend/client | partial |
| 18 | `moneybee-backend` | `appolon1908-hue/Moneybee-Backend` | `product-clients` | product caller | partial |
| 19 | `freight-frontend` | `appolon1908-hue/transportaion-Frontend` | `product-clients` | frontend/client | partial |
| 20 | `freight-backend` | `appolon1908-hue/transportation-backend-` | `product-clients` | product caller | partial |
| 21 | `larim-a-frontend` | `appolon1908-hue/LARIM-A-Fornt-end` | `product-clients` | frontend/client | partial |
| 22 | `larim-a-backend` | `appolon1908-hue/LARIM-A-Backend` | `product-clients` | product caller | partial |
| 23 | `telnexa-web` | `appolon1908-hue/Telnexa-web` | `product-clients` | public intake/onboarding | partial |
| 24 | `klyrow-web` | `appolon1908-hue/klyrow-Website-` | `product-clients` | public intake/onboarding | partial |
| 25 | `odoo` | `appolon1908-hue/Odoo` | `communications` | CRM/business adapter | contract defined |
| 26 | `keycloak` | `appolon1908-hue/Keycloak` | `edge-identity` | identity authority/compatibility | source partial |
| 27 | `middleware` | `appolon1908-hue/Middleware-` | `middleware-core` | cross-system authority | implemented foundation |
| 28 | `n8n` | `appolon1908-hue/N8N` | `automation` | orchestration caller only | contract defined |
| 29 | `vicidial-asterisk` | `appolon1908-hue/Vicidialer-Codestra` | `telephony-restricted` | voice adapter/event source | contract defined |
| 30 | `kong` | `appolon1908-hue/Kong` | `edge-identity` | gateway compatibility | source partial |
| 31 | `social` | `appolon1908-hue/social.codestra.co` | `communications` | social adapter/event source | contract defined |
| 32 | `sdk` | `appolon1908-hue/SDK-repository` | `governance` | API/SDK contract authority | source partial |
| 33 | `caddy` | `appolon1908-hue/Caddy` | `edge-identity` | edge/TLS compatibility | source partial |
| 34 | `documentation` | `appolon1908-hue/documentaions` | `governance` | documentation reference | active |
| 35 | `infrastructure` | `appolon1908-hue/Infustruction-repo` | `governance` | infrastructure coordinator | source partial |
| 36 | `communications-architecture` | `appolon1908-hue/communication-platform-` | `governance` | architecture/read-model authority | source partial |
| 37 | `grafana` | `appolon1908-hue/Codestra-Grafana-` | `analytics` | read-only observability UI | source partial |
| 38 | `prometheus` | `appolon1908-hue/Codestra-Prometheus` | `observability` | metrics backend | source partial |
| 39 | `alertmanager` | `appolon1908-hue/Codestra-Alertmanager` | `observability` | alert routing/handoff | source partial |
| 40 | `loki` | `appolon1908-hue/Codestra-Loki` | `observability` | logs backend | source partial |
| 41 | `telemetry` | `appolon1908-hue/Codestra-Telemetry` | `observability` | OTLP pipeline | source partial |
| 42 | `tempo` | `appolon1908-hue/Codestra-Tempo` | `observability` | traces backend | source partial |
| 43 | `superset` | `appolon1908-hue/Superset` | `analytics` | curated read-only analytics | source partial |
| 44 | `node-exporter` | `appolon1908-hue/Codestra-Node-Exporter` | `observability` | host metrics source | source partial |
| 45 | `cadvisor` | `appolon1908-hue/Codestra-cAdvisor` | `observability` | container metrics source | source partial |
| 46 | `redis-exporter` | `appolon1908-hue/Codestra-Redis-Exporter` | `observability` | Redis metrics source | source partial |
| 47 | `blackbox-exporter` | `appolon1908-hue/Codestra-Blackbox-Exporter` | `observability` | synthetic probe source | source partial |
| 48 | `alloy` | `appolon1908-hue/Codestra-Alloy` | `observability` | telemetry collection/forwarding | source partial |
| 49 | `openbao` | `appolon1908-hue/Codestra-OpenBao` | `secrets` | secrets/policy authority | blocked design |
| 50 | `postgres-exporter` | `appolon1908-hue/Codestra-Postgres-Exporter` | `observability` | PostgreSQL metrics source | source partial |
| 51 | `marketing-control-plane` | `appolon1908-hue/Codestra-Marketing-` | `planned-control-planes` | planned Middleware client | planned/disabled |
| 52 | `communications-control-center` | `appolon1908-hue/Codestra-Communication-CC` | `planned-control-planes` | planned operator client | planned/disabled |
| 53 | `social-control-plane` | `appolon1908-hue/Codesrea-Social-` | `planned-control-planes` | planned social client | name/authority review |
| 54 | `ai-control-plane` | `appolon1908-hue/Codestra-AI` | `planned-control-planes` | planned governed AI client | planned/disabled |

## Isolation cells

- **edge-identity:** Caddy, Kong, Keycloak. Owns TLS, routing policy, token issuance and validation compatibility—not business writes.
- **middleware-core:** Middleware command/operation ledgers, signed inbox, transactional outbox, audit, capability gates, reconciliation, and read-back.
- **automation:** n8n timing, branching, approvals, and SLA coordination. It never receives provider or database credentials.
- **communications:** Odoo, Klyrow, Telnexa, and Postiz behind governed adapters.
- **crawler:** Kyqra crawler command and signed result boundary.
- **telephony-restricted:** private VICIdial/Asterisk adapter with permanent campaign isolation.
- **financial-isolated:** Beyvra nonfinancial operations only; trading, order, wallet, ledger, and payment commands are prohibited.
- **product-clients:** product backends and same-origin public intake clients.
- **observability/analytics:** telemetry and read-only dashboards; no business mutation.
- **secrets:** OpenBao private secret authority; no default broad role or unreviewed initialization.
- **governance:** SDK, documentation, infrastructure, communications architecture, and historical evidence.
- **planned-control-planes:** future clients only; no provider runtime or credentials.
- **legacy-disabled:** preserved migration evidence, no runtime activation.

## Permanent integration rules

1. The owning repository is the principal source for its runtime or application.
2. Middleware may contain adapter translations, compatibility fixtures, and read-back/reconciliation logic; it must not duplicate destination runtime source.
3. Effectful callers require short-lived identity, tenant derivation, capability checks, semantic idempotency, durable command/operation records, and audit.
4. Provider callbacks require signature, timestamp, event ID, body digest, tenant mapping, and replay protection before acknowledgement.
5. A provider timeout after possible acceptance becomes `UNKNOWN`; it is never automatically retried.
6. Frontends and websites never receive Odoo, n8n, Postal, Jasmin, VICIdial, social-provider, database, or OpenBao credentials.
7. Observability and analytics read approved telemetry/read models only.
8. Legacy and placeholder repositories remain disabled until an explicit canonical-authority change is accepted.
9. All effectful capabilities remain false until a separate staging canary and production decision.

## Machine-readable sources

- `config/system-integration-registry.v3.json`
- `config/integration-cells.v1.json`
- `config/integration-status.v1.json`
- `config/repository-authorities.v1.json`
- `config/adapter-registry.v2.json`
- `config/control-plane-callers.v1.json`
- `connectors/manifests/*.connector.json`

This map is source governance only. It does not deploy Middleware, apply Kong/Keycloak/Caddy, install credentials, initialize OpenBao, activate n8n workflows, enable provider writes, or authorize production.
