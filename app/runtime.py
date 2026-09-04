from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .automation_policy import AutomationPolicy
from .automation_v2 import (
    AutomationService,
    MemoryAutomationStore,
    PostgresAutomationStore,
    WorkflowRouter,
)
from .commands import (
    CommandPolicyRegistry,
    CommandService,
    MemoryCommandStore,
    PostgresCommandStore,
)
from .communications import CommunicationsService, MemoryCommunicationsStore, PostgresCommunicationsStore
from .config import Settings
from .replay import MemoryReplayGuard, RedisReplayGuard, ReplayGuard
from .security import KeycloakJwtVerifier, TokenVerifier
from .storage import InboxStore, MemoryInboxStore, PostgresInboxStore

if TYPE_CHECKING:
    from .observability_incidents import IncidentService


@dataclass(frozen=True)
class ReadinessReport:
    components: dict[str, str]

    @property
    def ready(self) -> bool:
        return all(
            status in {"ready", "not_configured"}
            for status in self.components.values()
        )


@dataclass
class Runtime:
    settings: Settings
    inbox: InboxStore
    replay: ReplayGuard
    tokens: TokenVerifier
    commands: CommandService | None = None
    communications: CommunicationsService | None = None
    incidents: IncidentService | None = None
    automation: AutomationService | None = None

    async def readiness(self) -> ReadinessReport:
        checks: dict[str, Awaitable[bool] | None] = {
            "inbox_store": self.inbox.ready(),
            "replay_guard": self.replay.ready(),
            "identity_jwks": self.tokens.ready(),
        }
        if self.commands is not None:
            checks["command_store"] = self.commands.store.ready()
        else:
            checks["command_store"] = None
        checks["communications_store"] = (
            self.communications.store.ready() if self.communications is not None else None
        )
        checks["incident_store"] = (
            self.incidents.store.ready() if self.incidents is not None else None
        )
        checks["automation_store"] = (
            self.automation.ready() if self.automation is not None else None
        )

        async def bounded(check: Awaitable[bool] | None) -> str:
            if check is None:
                return "not_configured"
            try:
                result = await asyncio.wait_for(
                    check,
                    timeout=self.settings.readiness_timeout_seconds,
                )
            except Exception:
                return "not_ready"
            return "ready" if result is True else "not_ready"

        results = await asyncio.gather(
            *(bounded(check) for check in checks.values()),
        )
        return ReadinessReport(dict(zip(checks, results, strict=True)))

    async def ready(self) -> bool:
        return (await self.readiness()).ready

    async def close(self) -> None:
        await self.inbox.close()
        await self.replay.close()
        if self.communications is not None:
            await self.communications.store.close()
        if self.automation is not None:
            await self.automation.close()
        if self.commands is not None:
            await self.commands.store.close()
        if self.incidents is not None:
            await self.incidents.store.close()


async def build_runtime(settings: Settings) -> Runtime:
    tokens = KeycloakJwtVerifier(settings)
    command_policies = CommandPolicyRegistry.load()
    automation_policy = AutomationPolicy.from_path()
    workflow_router = WorkflowRouter.load()
    if settings.allow_in_memory_storage:
        commands = CommandService(
            store=MemoryCommandStore(),
            policies=command_policies,
        )
        automation = AutomationService(
            store=MemoryAutomationStore(),
            policy=automation_policy,
            workflow_router=workflow_router,
            commands=commands,
            umbrella_controls=settings.umbrella_controls,
        )
        return Runtime(
            settings=settings,
            inbox=MemoryInboxStore(),
            replay=MemoryReplayGuard(),
            tokens=tokens,
            commands=commands,
            communications=CommunicationsService(
                store=MemoryCommunicationsStore(),
                commands=commands,
                umbrella_controls=settings.umbrella_controls,
            ),
            automation=automation,
        )
    assert settings.database_url is not None
    assert settings.redis_url is not None
    inbox = await PostgresInboxStore.connect(settings.database_url)
    try:
        commands_store = await PostgresCommandStore.connect(settings.database_url)
        try:
            automation_store = await PostgresAutomationStore.connect(settings.database_url)
            try:
                replay = await RedisReplayGuard.connect(settings.redis_url)
            except Exception:
                await automation_store.close()
                raise
        except Exception:
            await commands_store.close()
            raise
    except Exception:
        await inbox.close()
        raise
    commands = CommandService(
        store=commands_store,
        policies=command_policies,
    )
    runtime = Runtime(
        settings=settings,
        inbox=inbox,
        replay=replay,
        tokens=tokens,
        commands=commands,
        automation=AutomationService(
            store=automation_store,
            policy=automation_policy,
            workflow_router=workflow_router,
            commands=commands,
            umbrella_controls=settings.umbrella_controls,
        ),
    )
    runtime.communications = CommunicationsService(
        store=await PostgresCommunicationsStore.connect(settings.database_url),
        commands=runtime.commands,
        umbrella_controls=settings.umbrella_controls,
    )
    if not await runtime.ready():
        await runtime.close()
        raise RuntimeError("mandatory runtime readiness checks failed during startup")
    return runtime
