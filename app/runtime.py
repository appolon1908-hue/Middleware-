from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .commands import (
    CommandPolicyRegistry,
    CommandService,
    MemoryCommandStore,
    PostgresCommandStore,
)
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
    commands: CommandService | None = None

    async def ready(self) -> bool:
        checks = [
            self.inbox.ready(),
            self.replay.ready(),
            self.tokens.ready(),
        ]
        if self.commands is not None:
            checks.append(self.commands.store.ready())
        results = await asyncio.gather(
            *checks,
            return_exceptions=True,
        )
        return all(result is True for result in results)

    async def close(self) -> None:
        await self.inbox.close()
        await self.replay.close()
        if self.commands is not None:
            await self.commands.store.close()


async def build_runtime(settings: Settings) -> Runtime:
    tokens = KeycloakJwtVerifier(settings)
    if settings.allow_in_memory_storage:
        return Runtime(
            settings=settings,
            inbox=MemoryInboxStore(),
            replay=MemoryReplayGuard(),
            tokens=tokens,
            commands=CommandService(
                store=MemoryCommandStore(),
                policies=CommandPolicyRegistry.load(),
            ),
        )
    assert settings.database_url is not None
    assert settings.redis_url is not None
    inbox = await PostgresInboxStore.connect(settings.database_url)
    try:
        commands = await PostgresCommandStore.connect(settings.database_url)
        try:
            replay = await RedisReplayGuard.connect(settings.redis_url)
        except Exception:
            await commands.close()
            raise
    except Exception:
        await inbox.close()
        raise
    runtime = Runtime(
        settings=settings,
        inbox=inbox,
        replay=replay,
        tokens=tokens,
        commands=CommandService(
            store=commands,
            policies=CommandPolicyRegistry.load(),
        ),
    )
    if not await runtime.ready():
        await runtime.close()
        raise RuntimeError("mandatory runtime readiness checks failed during startup")
    return runtime
