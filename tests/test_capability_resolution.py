from __future__ import annotations

import pytest

from app.capability_resolution import effective_capability_enabled


def capabilities() -> dict[str, object]:
    return {
        "runtime": {
            "ODOO_WRITE": True,
            "SMS_DELIVERY": False,
            "MALFORMED_RUNTIME": "true",
        },
        "umbrella_controls": {
            "EXTERNAL_DELIVERY_ENABLED": True,
            "LIVE_ADVERTISING_ENABLED": False,
            "MALFORMED_UMBRELLA": 1,
        },
        "LEGACY_BOOLEAN": True,
        "LEGACY_TRUTHY_STRING": "true",
    }


@pytest.mark.parametrize(
    "capability",
    [
        "ODOO_WRITE",
        "EXTERNAL_DELIVERY_ENABLED",
        "LEGACY_BOOLEAN",
    ],
)
def test_effective_capability_resolver_accepts_only_explicit_true(
    capability: str,
) -> None:
    assert effective_capability_enabled(capabilities(), capability) is True


@pytest.mark.parametrize(
    "capability",
    [
        "SMS_DELIVERY",
        "LIVE_ADVERTISING_ENABLED",
        "MALFORMED_RUNTIME",
        "MALFORMED_UMBRELLA",
        "LEGACY_TRUTHY_STRING",
        "UNKNOWN_CAPABILITY",
        "",
    ],
)
def test_effective_capability_resolver_fails_closed(
    capability: str,
) -> None:
    assert effective_capability_enabled(capabilities(), capability) is False


def test_nested_authority_overrides_legacy_top_level_value() -> None:
    values = capabilities()
    values["SMS_DELIVERY"] = True
    values["LIVE_ADVERTISING_ENABLED"] = True

    assert effective_capability_enabled(values, "SMS_DELIVERY") is False
    assert effective_capability_enabled(values, "LIVE_ADVERTISING_ENABLED") is False
