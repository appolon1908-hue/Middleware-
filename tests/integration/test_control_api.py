import hashlib, json, os
from pathlib import Path
import asyncpg, httpx, pytest
from app.main import create_app
from app.replay import MemoryReplayGuard
from app.runtime import Runtime
from app.storage import PostgresInboxStore
from tests.test_commands import CommandTokenVerifier

pytestmark=pytest.mark.skipif(os.getenv("RUNTIME_INTEGRATION_TESTS")!="1",reason="disposable integration only")

@pytest.mark.asyncio
async def test_durable_inbox_outbox_control_api_is_tenant_scoped_and_idempotent(test_settings):
    pool=await asyncpg.create_pool(os.environ["DATABASE_URL"])
    try:
        async with pool.acquire() as conn:
            for path in sorted(Path("migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")): await conn.execute(path.read_text())
            payload={"event_id":"full-api-event-1","tenant_id":"tenant-1"}; digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            await conn.execute("""INSERT INTO middleware_inbox(event_id,tenant_id,source_client_id,event_type,body_sha256,semantic_sha256,idempotency_key,correlation_id,payload,status) VALUES('full-api-event-1','tenant-1','odoo-integration','codestra.odoo.lead.updated',$1,$1,'full-api-event-1','full-api-correlation',$2::jsonb,'accepted') ON CONFLICT DO NOTHING""",digest,json.dumps(payload))
            await conn.execute("""INSERT INTO middleware_event_ledger(tenant_id,tenant_sequence,event_id,event_type,event_version,source_client_id,correlation_id,causation_id,idempotency_key,semantic_sha256,previous_entry_hash,entry_hash,payload) VALUES('tenant-1',999999,'full-api-event-1','codestra.odoo.lead.updated','1.0','odoo-integration','full-api-correlation','full-api-cause','full-api-event-1',$1,$2,$2,$3::jsonb) ON CONFLICT DO NOTHING""",digest,"0"*64,json.dumps(payload))
            outbox_id=await conn.fetchval("""INSERT INTO middleware_outbox(tenant_id,destination,event_type,payload,idempotency_key) VALUES('tenant-1','nats-jetstream','full.api.test','{}','full-api-outbox') ON CONFLICT(tenant_id,destination,idempotency_key) DO UPDATE SET event_type=EXCLUDED.event_type RETURNING id""")
        runtime=Runtime(settings=test_settings,inbox=PostgresInboxStore(pool),replay=MemoryReplayGuard(),tokens=CommandTokenVerifier())
        app=create_app(settings=test_settings,runtime=runtime)
        app.state.runtime=runtime
        transport=httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport,base_url="http://test") as client:
            read={"Authorization":"Bearer legacy-status-token","X-Tenant-ID":"tenant-1"}
            assert (await client.get("/v1/inbox",headers=read)).status_code==200
            assert (await client.get("/v1/outbox",headers=read)).status_code==200
            mutation={"Authorization":"Bearer legacy-command-token","X-Tenant-ID":"tenant-1","X-Correlation-ID":"full-api-correlation","Idempotency-Key":"full-api-mutation"}
            first=await client.post("/v1/inbox/full-api-event-1/quarantine",headers=mutation,json={"expected_version":1,"reason":"operator_review"})
            assert first.status_code==200 and first.json()["resource_version"]==2
            replay=await client.post("/v1/inbox/full-api-event-1/quarantine",headers=mutation,json={"expected_version":1,"reason":"operator_review"})
            assert replay.status_code==200 and replay.json()["resource_version"]==2
            changed=await client.post("/v1/inbox/full-api-event-1/quarantine",headers=mutation,json={"expected_version":1,"reason":"changed"})
            assert changed.status_code==409
            cancelled=await client.post(f"/v1/outbox/{outbox_id}/cancel",headers={**mutation,"Idempotency-Key":"full-api-outbox-cancel"},json={"expected_version":1,"reason":"operator_requested"})
            assert cancelled.status_code==200 and cancelled.json()["state"]=="CANCELLED"
    finally:
        await pool.close()
