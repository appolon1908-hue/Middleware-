from __future__ import annotations

from typing import Any

from .config import Settings


def runtime_safety_readback(settings: Settings) -> dict[str, Any]:
    """Return effective, non-secret controls from the immutable Settings object."""

    effects = dict(sorted(settings.external_effects.items()))
    provider_effects_disabled = not any(
        enabled for name, enabled in effects.items() if name != "SEND_EVENTS"
    )
    all_effects_disabled = not any(effects.values())
    staging_safe = (
        settings.app_env == "staging"
        and not settings.allow_in_memory_storage
        and all_effects_disabled
        and not settings.outbox_dispatch_enabled
        and settings.nats_dispatch_mode == "disabled"
        and settings.temporal_worker_mode == "disabled"
        and settings.production_dialing == "DISABLED"
        and settings.production_activation_id is None
    )
    return {
        "schema_version": "1.0",
        "service": "middleware-api",
        "environment": settings.app_env,
        "runtime_profile_id": settings.runtime_profile_id or "local-unlocked",
        "release": {
            "source_sha": settings.source_sha,
            "image_digest": settings.image_digest,
            "schema_head": settings.schema_head,
            "build_time": settings.build_time,
        },
        "persistence": {
            "in_memory": settings.allow_in_memory_storage,
        },
        "dispatch": {
            "outbox_enabled": settings.outbox_dispatch_enabled,
            "nats_mode": settings.nats_dispatch_mode,
            "temporal_worker_mode": settings.temporal_worker_mode,
        },
        "external_effects": effects,
        "production_dialing": settings.production_dialing,
        "production_activation_configured": (
            settings.production_activation_id is not None
        ),
        "provider_effects_disabled": provider_effects_disabled,
        "all_external_effects_disabled": all_effects_disabled,
        "staging_safe": staging_safe,
    }
