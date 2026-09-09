from __future__ import annotations

import base64
import json
from typing import Pattern

import pytest
from starlette.requests import Request

from app.control_api import (
    CORRELATION_ID_RE,
    IDEMPOTENCY_KEY_RE,
    MAX_BIGINT,
    TENANT_ID_RE,
    _cursor,
    _next,
    _authorization_header,
    _required_header,
)
from app.security import RequestValidationError


def _encode(value: object) -> str:
    payload = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _request(*headers: tuple[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [
                (name.lower().encode(), value.encode()) for name, value in headers
            ],
        }
    )


def test_cursor_round_trip_is_canonical_and_bounded() -> None:
    assert _cursor(None) is None
    assert _cursor(_next(1)) == 1
    assert _cursor(_next(MAX_BIGINT)) == MAX_BIGINT


@pytest.mark.parametrize("row_id", [True, 0, -1, MAX_BIGINT + 1])
def test_cursor_encoder_rejects_non_database_ids(row_id: int) -> None:
    with pytest.raises(ValueError, match="PostgreSQL bigint range"):
        _next(row_id)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "=",
        "A" * 129,
        _encode({"v": 1, "id": True}),
        _encode({"v": True, "id": 1}),
        _encode({"v": 1, "id": 0}),
        _encode({"v": 1, "id": MAX_BIGINT + 1}),
        _encode({"v": 1, "id": 1, "extra": False}),
        _next(1) + "=",
        _encode("not-an-object"),
        _encode({"v": 2, "id": 1}),
    ],
)
def test_cursor_rejects_malformed_or_noncanonical_values(value: str) -> None:
    with pytest.raises(RequestValidationError, match="cursor is malformed"):
        _cursor(value)


def test_cursor_rejects_duplicate_json_fields() -> None:
    duplicate = base64.urlsafe_b64encode(b'{"v":1,"id":1,"id":2}').decode().rstrip("=")
    with pytest.raises(RequestValidationError, match="cursor is malformed"):
        _cursor(duplicate)


def test_required_header_accepts_one_canonical_value() -> None:
    request = _request(("X-Tenant-ID", "tenant-1"))
    assert (
        _required_header(
            request,
            "X-Tenant-ID",
            maximum=64,
            pattern=TENANT_ID_RE,
        )
        == "tenant-1"
    )


@pytest.mark.parametrize(
    ("name", "value", "maximum", "pattern"),
    [
        ("X-Tenant-ID", " tenant-1", 64, TENANT_ID_RE),
        ("X-Tenant-ID", "tenant/other", 64, TENANT_ID_RE),
        ("X-Tenant-ID", "t" * 65, 64, TENANT_ID_RE),
        ("X-Correlation-ID", "contains space", 180, CORRELATION_ID_RE),
        ("Idempotency-Key", "short", 180, IDEMPOTENCY_KEY_RE),
    ],
)
def test_required_header_rejects_invalid_contract_values(
    name: str,
    value: str,
    maximum: int,
    pattern: Pattern[str],
) -> None:
    request = _request((name, value))
    with pytest.raises(RequestValidationError, match=f"{name} is malformed"):
        _required_header(
            request,
            name,
            maximum=maximum,
            pattern=pattern,
        )


def test_required_header_rejects_missing_and_duplicate_values() -> None:
    missing = _request()
    with pytest.raises(RequestValidationError, match="provided exactly once"):
        _required_header(missing, "X-Tenant-ID", maximum=64)

    duplicate = _request(
        ("Authorization", "Bearer first"),
        ("Authorization", "Bearer second"),
    )
    with pytest.raises(RequestValidationError, match="provided at most once"):
        _authorization_header(duplicate)


def test_authorization_header_preserves_missing_authentication_semantics() -> None:
    assert _authorization_header(_request()) == ""
    with pytest.raises(RequestValidationError, match="Authorization is malformed"):
        _authorization_header(_request(("Authorization", "x" * 8193)))
