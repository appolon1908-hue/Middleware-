import pytest

from app.core.vicidial_dispositions import POLICIES, disposition_policy


def test_required_statuses_have_unambiguous_complete_policies():
    required = {"SALE", "CALLBK", "BUSY", "NA", "NI", "DNC", "WRONG",
                "DISCONNECTED", "ANSWERED", "TRANSFER", "APPOINTMENT"}
    assert set(POLICIES) == required
    for policy in POLICIES.values():
        assert all((policy.odoo_disposition, policy.stage_action,
                    policy.activity_action, policy.callback_action,
                    policy.dnc_action, policy.required_note, policy.audit_event))


def test_answered_never_implies_sale_and_dnc_never_retries():
    assert disposition_policy("ANSWERED").stage_action == "no_stage_change"
    assert disposition_policy("ANSWERED").odoo_disposition != "sale"
    assert disposition_policy("DNC").retry_eligible is False
    assert disposition_policy("DNC").dnc_action == "set_and_suppress"


@pytest.mark.parametrize("alias,canonical", [("CB", "CALLBK"), ("WN", "WRONG"),
    ("DC", "DISCONNECTED"), ("XFER", "TRANSFER"), ("APPT", "APPOINTMENT")])
def test_vicidial_aliases_are_deterministic(alias, canonical):
    assert disposition_policy(alias) == POLICIES[canonical]


def test_unknown_status_fails_closed():
    with pytest.raises(ValueError, match="unsupported"):
        disposition_policy("UNKNOWN")
