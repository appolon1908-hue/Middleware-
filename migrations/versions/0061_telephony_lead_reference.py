"""Add lead_model/lead_id to telephony_call_lifecycle.

POST /v1/telephony/calls/originate already receives lead_model/lead_id in
its request body and records them into AuditEvent.redacted_payload, but
never onto telephony_call_lifecycle itself - the row GET /platform/v1/calls
actually reads. There was no way for a caller of that read API to learn
which CRM lead a call belongs to, short of joining through the audit
table's JSON payload (the same kind of workaround calls.py's own docstring
already flags as a real limitation for business_unit - not one to extend to
a third field). Odoo/codestra_middleware_bridge remains the system of
record for the lead/customer-profile record itself; these two columns are
only a reference, not a copy of CRM data.

Revision ID: 0061_telephony_lead_reference
Revises: 0060_agent_provisioning
"""

from alembic import op

revision = "0061_telephony_lead_reference"
down_revision = "0060_agent_provisioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE telephony_call_lifecycle "
        "ADD COLUMN lead_model varchar(64), "
        "ADD COLUMN lead_id integer"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE telephony_call_lifecycle "
        "DROP COLUMN lead_model, "
        "DROP COLUMN lead_id"
    )
