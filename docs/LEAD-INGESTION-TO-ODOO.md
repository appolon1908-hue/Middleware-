# Form, crawler, and scraper lead ingestion to Odoo

## Objective

All lead-producing systems use the middleware as the only write boundary to Odoo.

```text
website form / crawler result / approved scraper result
                    |
                    v
           edge and private gateway
                    |
                    v
             durable signed inbox
                    |
                    v
       core/lead-intake-normalization
                    |
                    v
 consent + suppression + provenance + dedupe + review policy
                    |
                    v
           transactional outbox
                    |
                    v
            integration/odoo-19
                    |
                    v
       Odoo contact, lead, activity, campaign, result
```

No website, crawler, scraper, n8n workflow, provider service, or browser test writes directly to Odoo.

## Public forms

The reviewed architecture includes form sources for Codestra, Beyvra, Booked4Seasons, Breero, Klyrow, and Telnexa.

A public form submission must include:

- authoritative tenant mapping;
- a stable submission and idempotency ID;
- correlation and causation IDs;
- capture time and source route;
- explicit consent status and channel choices;
- schema version;
- provenance showing that the person submitted the form;
- normalized contact or company data.

After validation, the middleware creates or updates the Odoo lead in the `new` stage. External contact is allowed only when consent and suppression policy pass.

## Crawler results

Kyqra crawler results enter through the private gateway and durable inbox. Each result includes the source reference, capture method, job ID, content digest when available, tenant, and provenance.

The middleware may create or update an Odoo record automatically, but the initial stage is:

```text
review_pending
```

The Odoo command must set:

```text
review_required=true
allow_external_contact=false
```

A crawler result cannot trigger SMS, email, dialing, social publication, or automated outreach merely because an Odoo record exists.

## Scraper results

The Codestra Business Scrapper is currently not deployed. Its branch and contract support readiness work only.

When activated through a separate approved change, scraper results follow the same review-pending policy as crawler results and require authoritative provenance. Imports without a valid tenant, source reference, legal-basis classification, or stable idempotency key are rejected or quarantined.

## Deduplication

The normalization service applies identifiers in this order:

1. tenant plus normalized email;
2. tenant plus normalized E.164 phone;
3. tenant plus normalized company domain and company name;
4. tenant plus source system and source record ID.

A duplicate submission reuses the original outcome. It does not create duplicate Odoo leads or repeat external delivery.

Conflicting identifiers are quarantined for review rather than silently merged.

## Odoo command

`contracts/odoo-lead-command.schema.json` defines the command delivered by the transactional outbox.

The Odoo adapter owns:

- tenant-to-company, sales-team, campaign, and source mapping;
- contact and company resolution;
- lead create/update;
- campaign and source tags;
- activity creation;
- review-stage enforcement;
- provenance note creation;
- result and error writeback;
- idempotency and reconciliation.

## Failure handling

A timeout is an unknown outcome. The adapter first reconciles using command and idempotency IDs. Only a proven non-delivery may be retried.

Retries are bounded. Exhausted work enters the dead-letter and operational-exception flow with an audited replay action.

## Safety controls

Staging must keep these capabilities disabled until the authoritative middleware source maps and enforces them:

```text
FORM_ODOO_DELIVERY_ENABLED=false
CRAWLER_ODOO_DELIVERY_ENABLED=false
SCRAPPER_ODOO_DELIVERY_ENABLED=false
CRAWLER_EXTERNAL_CONTACT_ENABLED=false
SCRAPPER_EXTERNAL_CONTACT_ENABLED=false
```

The application must fail closed when a required control is absent or malformed.

## Activation evidence

Before enabling a source:

- exact reviewed commit and image digest;
- authenticated route and tenant-mapping tests;
- consent and suppression tests;
- schema rejection tests;
- duplicate and collision tests;
- durable inbox and outbox tests;
- Odoo create/update and reconciliation tests;
- crawler/scraper review-pending enforcement;
- dead-letter and replay tests;
- backup/restore and rollback evidence;
- explicit production approval.
