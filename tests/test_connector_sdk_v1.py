"""Security and lifecycle regression tests for Codestra Connector SDK v1."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import time
import unittest
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from middleware.connector_sdk import (
    CapabilityDisabledError,
    CommandContext,
    CommandNotAllowedError,
    CommandOutcome,
    CommandRequest,
    CommandResult,
    ConnectionTestResult,
    ConnectorAdapter,
    ConnectorCatalogService,
    ConnectorHealth,
    ConnectorManifest,
    ConnectorRegistry,
    ConnectorRuntime,
    ConnectorState,
    InMemoryReplayStore,
    ManifestValidationError,
    MappingSecretResolver,
    NormalizedWebhookEvent,
    ReplayDetectedError,
    StaticCapabilityProvider,
    VerifiedWebhook,
    WebhookProcessor,
    WebhookRequest,
    WebhookVerificationError,
    manifest_digest,
    parse_manifest,
)
from middleware.connector_sdk.generation import build_generated_artifacts

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "connectors" / "manifests"


class FakeAdapter(ConnectorAdapter):
    def __init__(self, manifest: ConnectorManifest) -> None:
        self.manifest = manifest

    def validate_configuration(
        self, manifest: ConnectorManifest, configuration: Mapping[str, Any]
    ) -> tuple[str, ...]:
        del manifest
        return () if configuration.get("account_id") else ("account_id required",)

    def test_connection(
        self, manifest: ConnectorManifest, configuration: Mapping[str, Any]
    ) -> ConnectionTestResult:
        del manifest, configuration
        return ConnectionTestResult(ok=True, code="READ_ONLY_TEST_PASS")

    def execute_command(self, request: CommandRequest) -> CommandResult:
        return CommandResult(
            outcome=CommandOutcome.SUBMITTED,
            operation_id=request.command_id,
            safe_result={"submitted": True},
        )

    def read_back(
        self, request: CommandRequest, prior_result: CommandResult
    ) -> CommandResult:
        del request
        return CommandResult(
            outcome=CommandOutcome.COMPLETED,
            operation_id=prior_result.operation_id,
            safe_result={"readback": "confirmed"},
        )

    def normalize_webhook(self, webhook: VerifiedWebhook) -> NormalizedWebhookEvent:
        payload = json.loads(webhook.body)
        return NormalizedWebhookEvent(
            event_id=webhook.event_id,
            event_type=payload["event_type"],
            tenant_id=payload["tenant_id"],
            correlation_id=payload["correlation_id"],
            causation_id=payload["causation_id"],
            occurred_at=payload["occurred_at"],
            payload=payload,
        )

    def reconcile_unknown(
        self, request: CommandRequest, prior_result: CommandResult
    ) -> CommandResult:
        return self.read_back(request, prior_result)

    def health(self) -> ConnectorHealth:
        return ConnectorHealth(status="HEALTHY", checked_at_epoch=int(time.time()))


class ConnectorSdkV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ConnectorRegistry()
        self.records = self.registry.load_directory(MANIFESTS)

    @staticmethod
    def raw(connector_id: str) -> dict[str, Any]:
        return json.loads((MANIFESTS / f"{connector_id}.connector.json").read_text())

    def activate(self, connector_id: str) -> None:
        self.registry.set_state(
            connector_id,
            expected_state=ConnectorState.DECLARED,
            new_state=ConnectorState.ACTIVE,
        )
        self.registry.register_adapter_factory(connector_id, FakeAdapter)

    def request(self, tenant_id: str) -> CommandRequest:
        return CommandRequest(
            connector_id="klyrow-email",
            command_id=str(uuid.uuid4()),
            command_type="email.message.send.v1",
            command_version=1,
            payload={"message_id": "example"},
            context=CommandContext(
                tenant_id=tenant_id,
                actor_id="n8n-core-automation",
                correlation_id=str(uuid.uuid4()),
                causation_id=str(uuid.uuid4()),
                idempotency_key="email:test:0001",
                capability_snapshot={"EMAIL_DELIVERY": True},
            ),
        )

    def test_manifests_are_complete_disabled_and_non_overlapping(self) -> None:
        self.assertEqual(len(self.records), 8)
        self.assertEqual(self.registry.validate_global_invariants(), ())
        for record in self.records:
            self.assertFalse(record.manifest.enabled_by_default)
            self.assertFalse(record.manifest.direct_n8n_access)
            self.assertTrue(record.manifest.runtime_binding.base_url.endswith(".invalid"))

    def test_digest_is_stable_and_installation_is_disabled(self) -> None:
        raw = self.raw("postly-social")
        digest = manifest_digest(raw)
        self.assertEqual(digest, manifest_digest(copy.deepcopy(raw)))
        service = ConnectorCatalogService(ConnectorRegistry())
        projection = service.install_disabled(raw, expected_digest=digest)
        self.assertEqual(projection["state"], "INSTALLED_DISABLED")
        with self.assertRaises(ValueError):
            service.install_disabled(raw, expected_digest="sha256:" + "0" * 64)

    def test_manifest_rejects_secrets_and_unverified_public_urls(self) -> None:
        raw = self.raw("klyrow-email")
        raw["authentication"]["client_secret"] = "forbidden"
        with self.assertRaises(ManifestValidationError):
            parse_manifest(raw)
        raw = self.raw("klyrow-email")
        raw["runtime_binding"]["base_url"] = "https://email.example.com"
        with self.assertRaises(ManifestValidationError):
            parse_manifest(raw)

    def test_beyvra_financial_prefixes_are_unavailable(self) -> None:
        with self.assertRaises(CommandNotAllowedError):
            self.registry.resolve_command("trade.place.v1")
        record, policy = self.registry.resolve_command(
            "beyvra.operations.report-request.v1"
        )
        self.assertEqual(record.manifest.connector_id, "beyvra-nonfinancial")
        self.assertEqual(policy.required_capability, "BEYVRA_OPERATIONS_WRITE")

    def test_runtime_fails_closed_and_requires_readback(self) -> None:
        self.activate("klyrow-email")
        tenant_id = str(uuid.uuid4())
        request = self.request(tenant_id)
        with self.assertRaises(CapabilityDisabledError):
            ConnectorRuntime(
                self.registry, StaticCapabilityProvider({})
            ).execute(request)
        result = ConnectorRuntime(
            self.registry,
            StaticCapabilityProvider({(tenant_id, "EMAIL_DELIVERY"): True}),
        ).execute(request)
        self.assertEqual(result.outcome, CommandOutcome.COMPLETED)
        self.assertEqual(result.safe_result["readback"], "confirmed")

    def test_runtime_rejects_nested_secret_fields(self) -> None:
        self.activate("klyrow-email")
        tenant_id = str(uuid.uuid4())
        request = self.request(tenant_id)
        request = CommandRequest(
            connector_id=request.connector_id,
            command_id=request.command_id,
            command_type=request.command_type,
            command_version=1,
            payload={"nested": {"access_token": "forbidden"}},
            context=request.context,
        )
        with self.assertRaises(CommandNotAllowedError):
            ConnectorRuntime(
                self.registry,
                StaticCapabilityProvider({(tenant_id, "EMAIL_DELIVERY"): True}),
            ).execute(request)

    def test_webhook_hmac_timestamp_and_replay(self) -> None:
        self.activate("klyrow-email")
        secret = b"x" * 32
        now = int(time.time())
        payload = {
            "event_type": "email.message.delivered.v1",
            "tenant_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()),
            "causation_id": str(uuid.uuid4()),
            "occurred_at": "2026-08-27T21:00:00Z",
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
        signature = hmac.new(
            secret, str(now).encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        request = WebhookRequest(
            headers={
                "X-Postal-Signature": "v1=" + signature,
                "X-Postal-Timestamp": str(now),
                "X-Postal-Event-Id": "evt-1",
            },
            body=body,
            received_at_epoch=now,
        )
        processor = WebhookProcessor(
            self.registry,
            MappingSecretResolver({"WEBHOOK_POSTAL_HMAC_SECRET": secret}),
            InMemoryReplayStore(),
        )
        self.assertEqual(
            processor.process("klyrow-email", "postal-events", request).event_type,
            "email.message.delivered.v1",
        )
        with self.assertRaises(ReplayDetectedError):
            processor.process("klyrow-email", "postal-events", request)

    def test_reused_event_id_with_changed_body_is_a_conflict(self) -> None:
        self.activate("klyrow-email")
        secret = b"y" * 32
        now = int(time.time())
        processor = WebhookProcessor(
            self.registry,
            MappingSecretResolver({"WEBHOOK_POSTAL_HMAC_SECRET": secret}),
            InMemoryReplayStore(),
        )

        def request(body: bytes) -> WebhookRequest:
            signature = hmac.new(
                secret, str(now).encode() + b"." + body, hashlib.sha256
            ).hexdigest()
            return WebhookRequest(
                headers={
                    "X-Postal-Signature": signature,
                    "X-Postal-Timestamp": str(now),
                    "X-Postal-Event-Id": "evt-conflict",
                },
                body=body,
                received_at_epoch=now,
            )

        first = json.dumps({
            "event_type": "email.message.delivered.v1",
            "tenant_id": str(uuid.uuid4()),
            "correlation_id": str(uuid.uuid4()),
            "causation_id": str(uuid.uuid4()),
            "occurred_at": "2026-08-27T21:00:00Z",
        }).encode()
        processor.process("klyrow-email", "postal-events", request(first))
        with self.assertRaises(WebhookVerificationError):
            processor.process(
                "klyrow-email", "postal-events", request(first + b" ")
            )

    def test_generated_artifacts_match_manifests(self) -> None:
        artifacts = build_generated_artifacts(MANIFESTS)
        self.assertEqual(set(artifacts), {
            "kong-routes.v1.json",
            "keycloak-clients.v1.json",
            "n8n-workflow-packs.v1.json",
            "command-registry.v1.json",
        })
        self.assertEqual(len(artifacts["kong-routes.v1.json"]["routes"]), 8)

    def test_scaffold_output_parses_and_is_disabled(self) -> None:
        from scripts.scaffold_connector import build_manifest

        class Args:
            connector_id = "sample-api"
            display_name = "Sample API"
            repository = "appolon1908-hue/sample-api"
            cell = "core-communications"
            command_prefix = "sample."
            capability = "SAMPLE_WRITE"
            workflow_family = "product.sample-api"
            event_type = "sample.record.changed.v1"
            webhook_endpoint_key = "provider-events"

        manifest = parse_manifest(build_manifest(Args()))
        self.assertFalse(manifest.enabled_by_default)
        self.assertFalse(manifest.direct_n8n_access)


if __name__ == "__main__":
    unittest.main()
