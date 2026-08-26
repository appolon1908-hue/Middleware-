#!/usr/bin/env python3
from __future__ import annotations

import asyncio

from app.config import ConfigurationError, Settings


async def main() -> None:
    settings = Settings.from_env()
    if not settings.outbox_dispatch_enabled:
        raise ConfigurationError(
            "OUTBOX_DISPATCH_ENABLED=false; outbox worker is intentionally disabled"
        )
    raise ConfigurationError(
        "no external provider handlers are registered on intake-runtime-v1"
    )


if __name__ == "__main__":
    asyncio.run(main())
