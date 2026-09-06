"""Register the staging Odoo provider activity endpoint.

Revision ID: 0057_provider_activities
Revises: 0056_klyrow_delivery_events
"""

from alembic import op


revision = "0057_provider_activities"
down_revision = "0056_klyrow_delivery_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    INSERT INTO integration_endpoint(endpoint_id,service_id,endpoint_key,api_version)
    SELECT '55000000-0000-4000-8000-000000000021', service_id,
           'odoo.provider_activities.create','v1'
      FROM integration_service WHERE service_key='odoo'
    ON CONFLICT (service_id,endpoint_key,api_version) DO NOTHING
    """)
    op.execute("""
    INSERT INTO integration_schema_version
      (schema_version_id,service_key,endpoint_key,api_version,schema_reference,checksum,enabled)
    VALUES ('55000000-0000-4000-8000-000000000022','odoo',
      'odoo.provider_activities.create','v1',
      'internal://odoo/provider-activities/v1',
      'sha256:4bd760f2618d482757f7750b905f276f93391b8084231977980c3344231b4dbf',true)
    ON CONFLICT (service_key,endpoint_key,api_version) DO UPDATE SET enabled=true
    """)
    op.execute("""
    INSERT INTO integration_endpoint_version
      (endpoint_version_id,endpoint_id,configuration_version,base_url,path_template,http_method,
       content_type,authentication_mode,required_audience,required_scopes,credential_reference_id,
       tls_profile_id,timeout_ms,connection_timeout_ms,rate_limit_per_minute,concurrency_limit,
       idempotency_required,retry_class,retry_limit,redirects_allowed,target_attestation_required,
       stale_read_safe,enabled,kill_switch,configuration_checksum,effective_at,created_by,approved_by)
    VALUES ('55000000-0000-4000-8000-000000000023',
      '55000000-0000-4000-8000-000000000021',1,
      'http://odoo19-staging:8069','/api/v1/integration/provider-activities','POST',
      'application/json','oauth2_client_secret','codestra-odoo-integration',
      '["odoo.integration.results.write"]'::jsonb,
      'secret://staging/odoo-results-client','staging-internal',10000,3000,60,2,true,
      'BOUNDED_TRANSIENT_RETRY',3,false,false,false,true,false,
      'sha256:4bd760f2618d482757f7750b905f276f93391b8084231977980c3344231b4dbf',
      now(),'provider-webhook-pipeline','protected-review-required')
    ON CONFLICT (endpoint_id,configuration_version) DO NOTHING
    """)
    op.execute("""
    INSERT INTO integration_route_binding(binding_id,endpoint_version_id,environment)
    VALUES ('55000000-0000-4000-8000-000000000024',
      '55000000-0000-4000-8000-000000000023','staging')
    ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute(
        "DELETE FROM integration_route_binding WHERE binding_id::text LIKE '55000000-%'"
    )
    op.execute(
        "DELETE FROM integration_endpoint_version WHERE endpoint_version_id::text LIKE '55000000-%'"
    )
    op.execute(
        "DELETE FROM integration_schema_version WHERE schema_version_id::text LIKE '55000000-%'"
    )
    op.execute(
        "DELETE FROM integration_endpoint WHERE endpoint_id::text LIKE '55000000-%'"
    )
