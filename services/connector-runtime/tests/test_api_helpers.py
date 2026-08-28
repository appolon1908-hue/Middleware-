from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from codestra_connector_runtime.api.body_limits import read_bounded_body
from codestra_connector_runtime.api.config import RuntimeSettings
from codestra_connector_runtime.api.crypto import EncryptedBodyStore
from codestra_connector_runtime.api.cursor import CursorCodec
from codestra_connector_runtime.api.problems import ProblemError
from codestra_connector_runtime.api.repository import _etag_version
from starlette.requests import Request


def test_cursor_is_signed_and_tamper_evident() -> None:
    codec = CursorCodec(b"c" * 32)
    token = codec.encode({"after": "abc"})
    assert codec.decode(token) == {"after": "abc"}
    body, signature = token.split(".", 1)
    replacement = "A" if signature[-1] != "A" else "B"
    with pytest.raises(ProblemError):
        codec.decode(body + "." + signature[:-1] + replacement)


def test_etag_requires_positive_version() -> None:
    assert _etag_version('"v7"') == 7
    assert _etag_version('W/"v3"') == 3
    with pytest.raises(ProblemError):
        _etag_version(None)
    with pytest.raises(ProblemError):
        _etag_version('"v0"')


def test_encrypted_body_store_round_trip(tmp_path: Path) -> None:
    key_file = tmp_path / "key"
    key_file.write_bytes(base64.b64encode(b"k" * 32))
    store = EncryptedBodyStore.from_key_file(tmp_path / "bodies", key_file)
    body = b'{"event":"example"}'
    reference = store.persist(
        body,
        tenant_id="11111111-1111-4111-8111-111111111111",
        webhook_id="22222222-2222-4222-8222-222222222222",
        event_id="evt-1",
    )
    assert reference.startswith("file:")
    encrypted = (tmp_path / "bodies" / reference.removeprefix("file:")).read_bytes()
    assert body not in encrypted
    assert store.read(
        reference,
        tenant_id="11111111-1111-4111-8111-111111111111",
        webhook_id="22222222-2222-4222-8222-222222222222",
        event_id="evt-1",
        body_sha256=__import__("hashlib").sha256(body).hexdigest(),
    ) == body


def test_encrypted_body_store_reports_creation_and_deletes_safely(
    tmp_path: Path,
) -> None:
    key_file = tmp_path / "key"
    key_file.write_bytes(b"k" * 32)
    store = EncryptedBodyStore.from_key_file(tmp_path / "bodies", key_file)
    arguments = {
        "tenant_id": "11111111-1111-4111-8111-111111111111",
        "webhook_id": "22222222-2222-4222-8222-222222222222",
        "event_id": "evt-cleanup",
    }
    reference, created = store.persist_with_status(b"body", **arguments)
    same_reference, created_again = store.persist_with_status(
        b"body",
        **arguments,
    )
    assert same_reference == reference
    assert created is True
    assert created_again is False
    store.delete(reference)
    assert not (tmp_path / "bodies" / reference.removeprefix("file:")).exists()


def _streaming_request(
    chunks: list[bytes],
    *,
    content_length: int | None = None,
) -> tuple[Request, dict[str, int]]:
    state = {"receives": 0}
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]

    async def receive() -> dict[str, Any]:
        state["receives"] += 1
        return messages.pop(0)

    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode("ascii")))
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/test",
            "raw_path": b"/test",
            "query_string": b"",
            "headers": headers,
            "server": ("test", 443),
            "client": ("127.0.0.1", 1),
        },
        receive,
    )
    return request, state


@pytest.mark.asyncio
async def test_bounded_body_stops_stream_before_oversized_tail() -> None:
    request, state = _streaming_request([b"a" * 700, b"b" * 700, b"c" * 700])
    with pytest.raises(ProblemError) as captured:
        await read_bounded_body(
            request,
            maximum_bytes=1024,
            too_large_code="BODY_TOO_LARGE",
            title="Too large",
            detail="Too large.",
        )
    assert captured.value.status == 413
    assert state["receives"] == 2


@pytest.mark.asyncio
async def test_bounded_body_rejects_declared_size_before_receiving() -> None:
    request, state = _streaming_request(
        [b"not-read"],
        content_length=1025,
    )
    with pytest.raises(ProblemError) as captured:
        await read_bounded_body(
            request,
            maximum_bytes=1024,
            too_large_code="BODY_TOO_LARGE",
            title="Too large",
            detail="Too large.",
        )
    assert captured.value.status == 413
    assert state["receives"] == 0


def test_settings_are_fail_closed(tmp_path: Path) -> None:
    key_file = tmp_path / "key"
    key_file.write_bytes(b"x" * 32)
    settings = RuntimeSettings(
        database_url="postgresql+psycopg://example:example@localhost/example",
        cursor_hmac_key="y" * 32,
        body_encryption_key_file=key_file,
    )
    assert settings.connector_install_enabled is False
    assert settings.webhook_ingress_enabled is False
    assert settings.external_effects_enabled is False
    with pytest.raises(ValueError):
        RuntimeSettings(
            environment="production",
            database_url="postgresql+psycopg://example:example@localhost/example",
            cursor_hmac_key="y" * 32,
            body_encryption_key_file=key_file,
            connector_activation_enabled=True,
            release_sha="a" * 40,
        )


def test_settings_accept_documented_uppercase_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key_file = tmp_path / "key"
    key_file.write_bytes(b"x" * 32)
    monkeypatch.setenv(
        "CONNECTOR_RUNTIME_DATABASE_URL",
        "postgresql+psycopg://example:example@localhost/example",
    )
    monkeypatch.setenv("CONNECTOR_RUNTIME_CURSOR_HMAC_KEY", "y" * 32)
    monkeypatch.setenv(
        "CONNECTOR_RUNTIME_BODY_ENCRYPTION_KEY_FILE",
        str(key_file),
    )

    settings = RuntimeSettings()

    assert settings.database_url.get_secret_value().endswith("/example")
    assert settings.body_encryption_key_file == key_file
