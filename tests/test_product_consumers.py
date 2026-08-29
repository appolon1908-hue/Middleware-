from __future__ import annotations

import pytest

from app.commands import CommandEnvelope
from app.product_consumers import PRODUCT_CONSUMERS
from app.security import AuthorizationError, RequestValidationError

from .test_commands import command_payload


def test_moneybee_can_submit_middleware_telephony_and_crm_commands() -> None:
    for command_type, target, capability in (
        ("crm.contact.create.v1", "odoo-19", "ODOO_WRITE"),
        ("sms.message.submit.v1", "telnexa-sms", "SMS_DELIVERY"),
        ("telephony.dial.create.v1", "vicidial-restricted", "PRODUCTION_DIALING"),
    ):
        command = CommandEnvelope.model_validate(
            command_payload(
                command_type=command_type,
                target=target,
                capability=capability,
            )
        )
        consumer = PRODUCT_CONSUMERS.authorize(
            command,
            consumer_id="moneybee-backend",
            consumer_scope="moneybee.middleware.command.write",
        )
        assert consumer.client_id == "moneybee-backend"


def test_breero_and_transportation_are_limited_to_non_telephony_operations() -> None:
    command = CommandEnvelope.model_validate(
        command_payload(
            command_type="telephony.dial.create.v1",
            target="vicidial-restricted",
            capability="PRODUCTION_DIALING",
        )
    )
    for consumer_id, scope in (
        ("breero-backend", "breero.middleware.command.write"),
        ("transportation-backend", "transportation.middleware.command.write"),
        ("larim-a-backend", "larim-a.middleware.command.write"),
    ):
        with pytest.raises(AuthorizationError):
            PRODUCT_CONSUMERS.authorize(
                command,
                consumer_id=consumer_id,
                consumer_scope=scope,
            )


def test_product_consumer_registry_fails_closed() -> None:
    command = CommandEnvelope.model_validate(command_payload())
    with pytest.raises(RequestValidationError):
        PRODUCT_CONSUMERS.authorize(
            command,
            consumer_id=None,
            consumer_scope="moneybee.middleware.command.write",
        )
    with pytest.raises(AuthorizationError):
        PRODUCT_CONSUMERS.authorize(
            command,
            consumer_id="moneybee-backend",
            consumer_scope="wrong.scope",
        )
