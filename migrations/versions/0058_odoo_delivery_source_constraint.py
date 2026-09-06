"""Allow provider integration events as Odoo result delivery sources.

Revision ID: 0058_odoo_delivery_sources
Revises: 0057_provider_activities
"""

from alembic import op


revision = "0058_odoo_delivery_sources"
down_revision = "0057_provider_activities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_odoo_result_delivery_one_source",
        "odoo_result_delivery",
        type_="check",
    )
    op.create_check_constraint(
        "ck_odoo_result_delivery_one_source",
        "odoo_result_delivery",
        "num_nonnulls(acknowledgement_id, runtime_result_id, integration_event_id) = 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_odoo_result_delivery_one_source",
        "odoo_result_delivery",
        type_="check",
    )
    op.create_check_constraint(
        "ck_odoo_result_delivery_one_source",
        "odoo_result_delivery",
        "(acknowledgement_id IS NOT NULL) <> (runtime_result_id IS NOT NULL)",
    )
