"""Durable monitoring projections, replay records and resumable events.

Revision ID: 0058_integrated_monitoring
Revises: 0057_platform_service_catalog
"""

from alembic import op
import sqlalchemy as sa

revision = "0058_integrated_monitoring"
down_revision = "0057_platform_service_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "monitoring_resources",
        sa.Column("tenant", sa.String(128), primary_key=True),
        sa.Column("kind", sa.String(32), primary_key=True),
        sa.Column("resource_key", sa.String(512), primary_key=True),
        sa.Column("service_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("campaign_id", sa.String(128)),
        sa.Column("source_deployment", sa.String(128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_monitoring_resource_scope",
        "monitoring_resources",
        ["tenant", "kind", "service_id", "environment"],
    )
    op.create_table(
        "monitoring_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("operation", sa.String(256), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "tenant",
            "actor",
            "operation",
            "idempotency_key",
            name="uq_monitoring_operation_replay",
        ),
    )
    op.create_table(
        "monitoring_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant", sa.String(128), nullable=False),
        sa.Column("topic", sa.String(64), nullable=False),
        sa.Column("campaign_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_monitoring_event_scope", "monitoring_events", ["tenant", "id"])


def downgrade():
    raise RuntimeError(
        "Monitoring audit/replay evidence must be exported and restored through the reviewed recovery procedure; automatic destructive downgrade is disabled"
    )
