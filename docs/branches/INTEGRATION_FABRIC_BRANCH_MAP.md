# Integration fabric branch map

## Dependency order

1. `integration/n8n-control-plane-v2-20260827`
2. `architecture/codestra-integration-fabric-v2`
3. shared persistence and authorization primitives
4. one adapter branch per product
5. matching product-repository contract
6. matching n8n workflow pack
7. Kong route and Keycloak client changes
8. observability and negative tests
9. staging no-effect certification
10. immutable release and separate capability canary

## Focused implementation branches

```text
feat/tenant-onboarding-api-v1
feat/capability-registry-v1
feat/command-operation-api-v1
feat/webhook-inbox-v1
feat/transactional-outbox-v1
feat/event-delivery-ledger-v1
feat/dead-letter-replay-v1
integration/kong-cells-v1
integration/keycloak-service-identities-v2
integration/odoo-crm-facade-v1
integration/klyrow-email-v1
integration/telnexa-sms-v1
integration/postly-social-v1
integration/kyqra-crawler-v1
integration/vicidial-telephony-v1
integration/beyvra-nonfinancial-v1
integration/provisioning-service-v1
```

No branch is an environment. Do not force-update or delete existing historical branches. Cleanup requires a separate reachability and dependency review.