from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .config import Settings
from .replay import MemoryReplayGuard, RedisReplayGuard, ReplayGuard
from .security import KeycloakJwtVerifier, TokenVerifier
from .storage import InboxStore, MemoryInboxStore, PostgresInboxStore


@dataclass
class Runtime:
    settings: Settings
    inbox: InboxStore
    replay: ReplayGuard
    tokens: TokenVerifier

    async def ready(self) -> bool:
        results = await asyncio.gather(
            self.inbox.ready(),
            self.replay.ready(),
            self.tokens.ready(),
            return_exceptions=True,
        )
        return all(result is True for result in results)

    async def close(self) -> None:
        await self.inbox.close()
        await self.replay.close()


async def build_runtime(settings: Settings) -> Runtime:
    tokens = KeycloakJwtVerifier(settings)
    if settings.allow_in_memory_storage:
        return Runtime(
            settings=settings,
            inbox=MemoryInboxStore(),
            replay=MemoryReplayGuard(),
            tokens=tokens,
        )
    assert settings.database_url is not None
    assert settings.redis_url is not None
    inbox = await PostgresInboxStore.connect(settings.database_url)
    try:
        replay = await RedisReplayGuard.connect(settings.redis_url)
    except Exception:
        await inbox.close()
        raise
    runtime = Runtime(settings=settings, inbox=inbox, replay=replay, tokens=tokens)
    if not await runtime.ready():
        await runtime.close()
        raise RuntimeError("mandatory runtime readiness checks failed during startup")
    return runtime
