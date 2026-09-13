"""Durable normalized business event inbox.

Revision ID: 0061_codestra_business_events
Revises: 0060_agent_provisioning
"""
from alembic import op

revision = "0061_codestra_business_events"
down_revision = "0060_agent_provisioning"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE codestra_business_event_inbox (
      source varchar(32) NOT NULL, tenant_id varchar(200) NOT NULL,
      event_id varchar(200) NOT NULL, payload_hash varchar(64) NOT NULL,
      payload json NOT NULL, state varchar(24) NOT NULL DEFAULT 'PENDING',
      received_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (source,tenant_id,event_id),
      CHECK (state IN ('PENDING','PROCESSING','COMPLETE','RETRY','DEAD_LETTER'))
    )""")
    op.execute("CREATE INDEX ix_business_event_pending ON codestra_business_event_inbox(state,received_at)")


def downgrade():
    # Retain accepted facts on rollback; destructive removal requires a
    # separate retention decision after export/drain, never an automatic DROP.
    raise RuntimeError("accepted_business_events_require_explicit_retention_review")
