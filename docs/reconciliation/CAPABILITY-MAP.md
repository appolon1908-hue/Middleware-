# Capability Map

Frozen inputs: canonical main `844d13c7ba808653a7d982c63353bc67cdc9adef`; server capture `85b7898456abd4bdd0928b80ea925cafd8ad0f4c`; captured original source `7b9451b4db92982e5f0a4179d979ae94c043f943`. This document is analysis only.

All effectful operations default to deny. Tenant and environment are mandatory command attributes, and staging external-effect capabilities remain disabled.

| CURRENT_SERVER_PATH | TARGET_CAPABILITY | DEFAULT | TENANT | CONNECTOR | ENVIRONMENT | COMMAND_TYPE |
|---|---|---|---|---|---|---|
| Odoo customer/lead/result writes | odoo.customer.write / odoo.lead.write / odoo.result.write | DENY | verified tenant required | odoo | explicit; live disabled outside approved production | odoo.command |
| n8n dispatch | n8n.workflow.dispatch | DENY | verified tenant required | n8n | explicit; live disabled outside approved production | n8n.workflow.dispatch |
| SMS dispatch | sms.send | DENY | verified tenant required | communications | explicit; live disabled outside approved production | sms.send |
| email dispatch | email.send | DENY | verified tenant required | communications | explicit; live disabled outside approved production | email.send |
| callback dispatch | callback.execute | DENY | verified tenant required | callback | explicit; live disabled outside approved production | callback.execute |
| call start/control | telephony.call.start / telephony.call.control | DENY | verified tenant required | vicidial | explicit; live disabled outside approved production | telephony.command |
| extension allocation/provisioning | telephony.extension.provision | DENY | verified tenant required | provisioning | explicit; live disabled outside approved production | provisioning.desired_state |
| webphone session | telephony.session.issue | DENY | verified tenant required | webphone | explicit; live disabled outside approved production | telephony.session.issue |
| social publish/cancel | social.publish / social.cancel | DENY | verified tenant required | postiz-postly | explicit; live disabled outside approved production | social.command |
| scraper/Breero intake to CRM | crm.lead.ingest / odoo.lead.write | DENY | verified tenant required | kyqra-breero-odoo | explicit; live disabled outside approved production | lead.ingest |
| dead-letter replay | event.replay | DENY | verified tenant required | runtime | explicit; live disabled outside approved production | replay.command |
| campaign activation | campaign.activate | DENY | verified tenant required | runtime | explicit; live disabled outside approved production | activation.command |
