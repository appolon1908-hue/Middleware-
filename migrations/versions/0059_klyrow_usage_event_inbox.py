"""Add the durable Klyrow usage-event inbox.

Revision ID: 0059_klyrow_usage_events
Revises: 0058_odoo_delivery_sources
"""

from alembic import op


revision = "0059_klyrow_usage_events"
down_revision = "0058_odoo_delivery_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE klyrow_usage_event_inbox (
      event_id text PRIMARY KEY,
      payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
      received_at timestamptz NOT NULL DEFAULT now(),
      tenant_id text NOT NULL,
      message_id text NOT NULL,
      stream text NOT NULL CHECK (stream IN ('transactional','security','system','marketing','bulk')),
      billable_units bigint NOT NULL CHECK (billable_units >= 0),
      provider_result_category text NOT NULL,
      payload jsonb NOT NULL,
      status text NOT NULL DEFAULT 'complete' CHECK (status IN ('complete'))
    )
    """)
    op.execute(
        "CREATE INDEX ix_klyrow_usage_inbox_tenant_received "
        "ON klyrow_usage_event_inbox(tenant_id,received_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE klyrow_usage_event_inbox")
