"""Durable encrypted raw-webhook body storage."""

from __future__ import annotations

import base64
import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True, slots=True)
class EncryptedBodyStore:
    root: Path
    key: bytes

    @classmethod
    def from_key_file(cls, root: Path, key_file: Path) -> "EncryptedBodyStore":
        raw = key_file.read_bytes().strip()
        try:
            decoded = base64.b64decode(raw, validate=True)
        except Exception:
            decoded = raw
        if len(decoded) not in {16, 24, 32}:
            raise ValueError("body encryption key must be 16, 24, or 32 bytes")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        return cls(root=root, key=decoded)

    def persist(
        self,
        body: bytes,
        *,
        tenant_id: str,
        webhook_id: str,
        event_id: str,
    ) -> str:
        body_digest = hashlib.sha256(body).hexdigest()
        safe_event = hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:24]
        relative = Path(tenant_id) / webhook_id / f"{safe_event}-{body_digest}.bin"
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(target.parent, 0o700)
        if target.exists():
            return "file:" + relative.as_posix()

        nonce = os.urandom(12)
        associated = (
            f"{tenant_id}:{webhook_id}:{event_id}:{body_digest}"
        ).encode("utf-8")
        ciphertext = AESGCM(self.key).encrypt(nonce, body, associated)
        payload = b"CRB1" + nonce + ciphertext
        file_descriptor, temporary_path = tempfile.mkstemp(
            prefix=".pending-",
            dir=target.parent,
        )
        try:
            with os.fdopen(file_descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, target)
            # POSIX permits opening and fsyncing a directory so the rename is
            # durable across a host crash. Windows does not expose that
            # operation through os.open; the file fsync above remains valid.
            if os.name != "nt":
                directory_fd = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
        return "file:" + relative.as_posix()

    def read(
        self,
        reference: str,
        *,
        tenant_id: str,
        webhook_id: str,
        event_id: str,
        body_sha256: str,
    ) -> bytes:
        if not reference.startswith("file:"):
            raise ValueError("unsupported encrypted body reference")
        relative = Path(reference.removeprefix("file:"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid encrypted body reference")
        payload = (self.root / relative).read_bytes()
        if len(payload) < 4 + 12 + 16 or payload[:4] != b"CRB1":
            raise ValueError("encrypted body record is invalid")
        nonce = payload[4:16]
        ciphertext = payload[16:]
        associated = (
            f"{tenant_id}:{webhook_id}:{event_id}:{body_sha256}"
        ).encode("utf-8")
        body = AESGCM(self.key).decrypt(nonce, ciphertext, associated)
        if hashlib.sha256(body).hexdigest() != body_sha256:
            raise ValueError("encrypted body digest does not match")
        return body
