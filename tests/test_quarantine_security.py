import json

import pytest

from app.core.quarantine import (
    EncryptedPayload,
    QuarantineIntegrityError,
    decrypt_payload,
    encrypt_payload,
    fingerprint,
    sanitized_preview,
    transition,
)


def test_keyed_fingerprint_encryption_and_integrity():
    raw = b'{"event_id":"synthetic","telephone_number":"+18095550123"}'
    fingerprint_key = b"f" * 32
    encryption_key = b"e" * 32
    digest = fingerprint(raw, fingerprint_key)
    encrypted = encrypt_payload(raw, encryption_key, "test-v1", digest)
    assert encrypted.ciphertext != raw
    assert raw not in encrypted.ciphertext
    assert decrypt_payload(encrypted, encryption_key, digest, fingerprint_key) == raw
    tampered = EncryptedPayload(
        encrypted.ciphertext[:-1] + bytes([encrypted.ciphertext[-1] ^ 1]),
        encrypted.nonce,
        encrypted.key_version,
    )
    with pytest.raises(QuarantineIntegrityError):
        decrypt_payload(tampered, encryption_key, digest, fingerprint_key)
    with pytest.raises(QuarantineIntegrityError):
        decrypt_payload(encrypted, encryption_key, "0" * 64, fingerprint_key)


def test_preview_never_contains_raw_pii_or_secrets():
    raw = json.dumps({
        "event_id": "synthetic-event",
        "event_type": "synthetic.publisher_canary",
        "business_unit": "MOY",
        "telephone_number": "+18095550123",
        "authorization": "Bearer do-not-leak",
        "payload": {"email": "customer@example.invalid"},
    }).encode()
    preview = sanitized_preview(raw)
    serialized = json.dumps(preview)
    assert "synthetic.publisher_canary" in serialized
    for secret in ("+18095550123", "do-not-leak", "customer@example.invalid"):
        assert secret not in serialized


def test_malformed_preview_is_bounded_metadata_only():
    raw = b"{not-json:secret-value}"
    assert sanitized_preview(raw) == {
        "format": "invalid-json",
        "byte_length": len(raw),
    }


def test_controlled_state_machine_rejects_shortcuts_and_duplicate_replay():
    transition("PENDING_REVIEW", "UNDER_REVIEW")
    transition("UNDER_REVIEW", "REPLAY_APPROVED")
    transition("REPLAY_APPROVED", "REPLAYING")
    transition("REPLAYING", "REPLAYED")
    with pytest.raises(ValueError):
        transition("PENDING_REVIEW", "REPLAYING")
    with pytest.raises(ValueError):
        transition("REPLAYED", "REPLAYING")
