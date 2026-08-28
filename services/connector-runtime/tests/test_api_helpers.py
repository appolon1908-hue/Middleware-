from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from codestra_connector_runtime.api.config import RuntimeSettings
from codestra_connector_runtime.api.crypto import EncryptedBodyStore
from codestra_connector_runtime.api.cursor import CursorCodec
from codestra_connector_runtime.api.problems import ProblemError
from codestra_connector_runtime.api.repository import _etag_version


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
