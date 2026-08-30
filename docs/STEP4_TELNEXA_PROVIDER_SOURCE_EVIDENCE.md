# Step 4 — Telnexa Provider Source Evidence

## Authority

```text
SDK_CONTRACT_SHA=63c793e88cca5daecfb5c8a688b8674ab288c522
MIDDLEWARE_BASE_SHA=d9735422796cb2aa18a39339aad3cc87bdf67ba9
TELNEXA_SOURCE_SHA=ee4cea8e6d15a5ba24c1f37d0ede60df67eaa151
TELNEXA_SYNTHETIC_MERGE_SHA=b3e3e09597b5113ba44cef56686025aa1bd0cbbd
TELNEXA_PROMOTION_PR=22
```

Middleware owns cross-system identity, authorization, tenancy, consent, suppression, canonical command state, idempotency, and reconciliation coordination. Telnexa owns Jasmin translation, provider submission evidence, provider references, billing reservations, DLR/MO normalization, local STOP/HELP evidence, and provider read-back.

## Provider certification

Telnexa exact head `ee4cea8e6d15a5ba24c1f37d0ede60df67eaa151` passed:

- exact-head CI run `33338423307`;
- Step 4 provider certification run `33338423309`;
- exact source and synthetic merge-result validation;
- formatting, lint, full tests, dependency audit, Compose validation, and non-root image build;
- Gitleaks PR-range scan;
- PostgreSQL migration, tenant-policy, and one-submit assertions;
- internal no-effect Jasmin simulation;
- one provider submission attempt and zero blind resubmissions;
- stale `submitting` recovery through authoritative read-back only;
- serialized reconciliation attempt claims and evidence inserts;
- durable provider-reference requirement before billing commitment;
- all live-effect flags disabled.

All four review findings were addressed and their threads were resolved on the exact certified source head. Protected Telnexa promotion remains subject to independent approval and is not treated as deployment authorization.

## Cross-repository lock

`config/telnexa-sms-provider-source-lock.v1.json` is the machine-readable authority consumed by Middleware tests. Any change to the SDK contract, Middleware command mapping, Telnexa source head, reconciliation policy, or live-effect flags requires a new review and complete rerun.

## Safety

```text
SMS_DELIVERY=false
SMS_DELIVERY_ENABLED=false
LIVE_SMS_DELIVERY=false
JASMIN_LIVE_SUBMISSION=false
CALLBACK_DISPATCH_ENABLED=false
SMS_SENT=NO
PRODUCTION_DEPLOYED=NO
SERVER_CHANGED=NO
```

This evidence is source-only. It does not install credentials, apply a database migration to a server, establish an SMPP bind, mutate live billing, send SMS, or deploy production.
