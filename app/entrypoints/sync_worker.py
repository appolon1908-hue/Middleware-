"""Odoo synchronization worker; remains idle while delivery is disabled."""
from app.core.config import settings
from app.entrypoints.runtime import run_worker


SERVICE = "middleware-sync-worker"
QUEUE = "middleware.sync.odoo.v1"


async def cycle() -> dict[str, object]:
    return {"status": "disabled" if not settings.odoo_delivery_enabled else "idle"}


if __name__ == "__main__":
    run_worker(SERVICE, QUEUE, cycle)
