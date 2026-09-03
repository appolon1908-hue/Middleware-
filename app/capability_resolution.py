from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_CAPABILITY_SECTIONS = ("runtime", "umbrella_controls")


def effective_capability_enabled(
    capabilities: Mapping[str, Any],
    capability: str,
) -> bool:
    """Resolve one effective capability without truthy coercion.

    Runtime implementation controls and umbrella controls are authoritative.
    Legacy top-level booleans are accepted only as a compatibility fallback.
    Unknown, malformed, nested, or non-boolean values always fail closed.
    """

    if not isinstance(capability, str) or not capability or len(capability) > 100:
        return False

    for section_name in _CAPABILITY_SECTIONS:
        section = capabilities.get(section_name)
        if isinstance(section, Mapping) and capability in section:
            return section[capability] is True

    value = capabilities.get(capability)
    return value is True
