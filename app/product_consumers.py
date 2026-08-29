from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .commands import CommandEnvelope
from .security import AuthorizationError, RequestValidationError


ROOT = Path(__file__).resolve().parents[1]
CONSUMER_PATH = ROOT / "config" / "product-consumers.v1.json"


@dataclass(frozen=True)
class ProductConsumer:
    client_id: str
    required_scope: str
    allowed_command_prefixes: tuple[str, ...]
    forbidden_command_prefixes: tuple[str, ...]


class ProductConsumerRegistry:
    def __init__(self, consumers: tuple[ProductConsumer, ...]) -> None:
        self._consumers = {consumer.client_id: consumer for consumer in consumers}

    @classmethod
    def load(cls) -> "ProductConsumerRegistry":
        raw = json.loads(CONSUMER_PATH.read_text(encoding="utf-8"))
        if raw.get("schema_version") != "1.0" or raw.get("default_policy") != "DENY":
            raise ValueError("product consumer registry must be schema 1.0 with DENY default")
        consumers = raw.get("consumers")
        if not isinstance(consumers, list) or not consumers:
            raise ValueError("product consumer registry must declare consumers")
        parsed = []
        seen = set()
        for item in consumers:
            if not isinstance(item, dict):
                raise ValueError("product consumer entry must be an object")
            client_id = _required_string(item, "client_id")
            if client_id in seen:
                raise ValueError(f"duplicate product consumer {client_id}")
            seen.add(client_id)
            allowed = _required_string_list(item, "allowed_command_prefixes")
            forbidden = _required_string_list(item, "forbidden_command_prefixes")
            if set(allowed) & set(forbidden):
                raise ValueError(f"consumer {client_id} overlaps allowed and forbidden prefixes")
            parsed.append(
                ProductConsumer(
                    client_id=client_id,
                    required_scope=_required_string(item, "required_scope"),
                    allowed_command_prefixes=tuple(allowed),
                    forbidden_command_prefixes=tuple(forbidden),
                )
            )
        return cls(tuple(parsed))

    def authorize(
        self,
        command: CommandEnvelope,
        *,
        consumer_id: str | None,
        consumer_scope: str | None,
    ) -> ProductConsumer:
        if consumer_id is None or not consumer_id.strip():
            raise RequestValidationError("X-Codestra-Consumer-Id is required")
        if consumer_scope is None or not consumer_scope.strip():
            raise RequestValidationError("X-Codestra-Consumer-Scope is required")
        consumer = self._consumers.get(consumer_id.strip())
        if consumer is None:
            raise AuthorizationError("product consumer is not registered")
        scopes = set(consumer_scope.split())
        if consumer.required_scope not in scopes:
            raise AuthorizationError("product consumer scope is not allowed")
        if any(
            command.command_type.startswith(prefix)
            for prefix in consumer.forbidden_command_prefixes
        ):
            raise AuthorizationError("product consumer command prefix is forbidden")
        if not any(
            command.command_type.startswith(prefix)
            for prefix in consumer.allowed_command_prefixes
        ):
            raise AuthorizationError("product consumer command prefix is not allowed")
        return consumer


def _required_string(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"product consumer {key} must be a non-empty string")
    return value.strip()


def _required_string_list(item: dict[str, object], key: str) -> list[str]:
    value = item.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(entry, str) and entry.strip() for entry in value)
    ):
        raise ValueError(f"product consumer {key} must be a non-empty string list")
    return [entry.strip() for entry in value]


PRODUCT_CONSUMERS = ProductConsumerRegistry.load()
