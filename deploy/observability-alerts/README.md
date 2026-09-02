# Middleware observability-alert service

This deployment is a narrow API/worker binding built from the canonical Middleware image. It belongs on the core application host (`65.109.65.169`), not on the provider host. Alertmanager on `37.27.128.39` reaches it over the approved private network; the Middleware worker then reaches the Klyrow email API over mTLS.

The production request path is:

```text
Prometheus -> Alertmanager -> Middleware alert API -> durable command/outbox
           -> Temporal command worker -> Klyrow alert adapter -> Klyrow API
           -> alerts@codestra.co -> appolon@codestra.co
```

`OBSERVABILITY_ALERT_EMAIL_DELIVERY` is independent from general customer, campaign, and bulk delivery. The following must remain false for the initial alert-only activation:

```text
LIVE_EMAIL_DELIVERY=false
ENABLE_EXTERNAL_DELIVERY=false
EMAIL_DELIVERY_ENABLED=false
```

The Compose file is source authority only. It requires an exact immutable Middleware image, a protected source SHA, and secret files rendered by OpenBao. Do not deploy from this branch. Production installation requires protected merge, signed image, staging certification, backup, rollback, and a separate activation record.
