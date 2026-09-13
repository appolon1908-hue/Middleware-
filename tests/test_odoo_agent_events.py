from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.models import EventEnvelope
from app.odoo_agent_events import (
    ODOO_AGENT_EVENT_TYPES,
    OdooAgentEventValidationError,
    validate_odoo_agent_event,
)


def _envelope(event_type: str, payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope.model_validate(
        {
            "event_id": "event-agent-123456789",
            "event_type": event_type,
            "event_version": "1.0",
            "occurred_at": datetime(2026, 9, 12, tzinfo=timezone.utc),
            "received_at": datetime(2026, 9, 12, tzinfo=timezone.utc),
            "source": "odoo-integration",
            "tenant_id": "tenant-agent-test",
            "correlation_id": "corr-agent-test",
            "causation_id": "cause-agent-test",
            "idempotency_key": "event-agent-123456789",
            "payload": payload,
            "metadata": {},
        }
    )


def _controls() -> dict[str, bool]:
    return {
        "create_disabled": True,
        "activate_immediately": False,
        "send_activation_email": False,
        "plaintext_password_allowed": False,
        "browser_campaign_selection_allowed": False,
        "change_agent_campaign": False,
        "production_dialing": False,
        "live_call_control": False,
        "webrtc_credential_issuance": False,
    }


class OdooAgentEventValidationTests(unittest.TestCase):
    def test_exact_public_event_types(self) -> None:
        self.assertEqual(
            ODOO_AGENT_EVENT_TYPES,
            {
                "codestra.odoo.agent.provisioning_requested",
                "codestra.odoo.agent.activation_email_requested",
            },
        )

    def test_provisioning_payload_is_accepted(self) -> None:
        validate_odoo_agent_event(
            _envelope(
                "codestra.odoo.agent.provisioning_requested",
                {
                    "schema_version": "1.0",
                    "event_type": "agent.provisioning.requested.v1",
                    "onboarding_uuid": "onboarding-1",
                    "login_identifier": "agent@example.com",
                    "recipient_email": "agent@example.com",
                    "targets": ["odoo", "keycloak", "email_provider"],
                    "telephony_assignment": {
                        "extension": None,
                        "webrtc_enabled": False,
                        "sms_enabled": False,
                        "webrtc_max_devices": 1,
                    },
                    "controls": _controls(),
                },
            )
        )

    def test_activation_payload_requires_credential_free_login_url(self) -> None:
        payload = {
            "schema_version": "1.0",
            "event_type": "agent.activation-email.requested.v1",
            "onboarding_uuid": "onboarding-1",
            "login_identifier": "agent@example.com",
            "delivery": {
                "channel": "email",
                "provider": "klyrow",
                "mode": "keycloak_execute_actions_email",
                "template_key": "agent-welcome-v1",
                "recipient": "agent@example.com",
                "preferred_language": "en_US",
            },
            "login": {
                "identifier": "agent@example.com",
                "url": "https://login.example.test/activate",
                "required_actions": ["UPDATE_PASSWORD", "CONFIGURE_TOTP"],
                "expires_in_minutes": 30,
            },
            "controls": {
                "one_time_action_required": True,
                "plaintext_password_allowed": False,
                "link_persistence_allowed": False,
                "activate_immediately": False,
                "production_dialing": False,
            },
        }
        validate_odoo_agent_event(
            _envelope(
                "codestra.odoo.agent.activation_email_requested",
                payload,
            )
        )
        payload["login"] = {
            **payload["login"],
            "url": "https://login.example.test/activate?token=forbidden",
        }
        with self.assertRaisesRegex(
            OdooAgentEventValidationError,
            "credential-free HTTPS",
        ):
            validate_odoo_agent_event(
                _envelope(
                    "codestra.odoo.agent.activation_email_requested",
                    payload,
                )
            )

    def test_agent_payload_rejects_credentials_and_action_links(self) -> None:
        payload = {
            "schema_version": "1.0",
            "event_type": "agent.provisioning.requested.v1",
            "onboarding_uuid": "onboarding-1",
            "login_identifier": "agent@example.com",
            "recipient_email": "agent@example.com",
            "targets": ["odoo"],
            "telephony_assignment": {
                "extension": None,
                "webrtc_enabled": False,
                "sms_enabled": False,
                "webrtc_max_devices": 1,
            },
            "controls": {
                **_controls(),
                "password": False,
            },
        }
        with self.assertRaisesRegex(
            OdooAgentEventValidationError,
            "forbidden fields: password",
        ):
            validate_odoo_agent_event(
                _envelope(
                    "codestra.odoo.agent.provisioning_requested",
                    payload,
                )
            )
