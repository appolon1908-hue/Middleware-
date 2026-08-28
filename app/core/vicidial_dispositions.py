"""Deterministic VICIdial-to-Odoo disposition policy.

The mapping is data-only and side-effect free so ingestion, Odoo delivery,
reconciliation, and tests use exactly the same business rules.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DispositionPolicy:
    odoo_disposition: str
    stage_action: str
    activity_action: str
    retry_eligible: bool
    callback_action: str
    dnc_action: str
    required_note: str
    audit_event: str


POLICIES = {
    "SALE": DispositionPolicy("sale", "mark_qualified_sale", "close_open_call_activities", False, "clear", "preserve", "Sale confirmed by VICIdial", "odoo.disposition.sale.v1"),
    "CALLBK": DispositionPolicy("callback", "no_stage_change", "create_callback_activity", False, "require_datetime", "preserve", "Callback requested", "odoo.disposition.callback.v1"),
    "BUSY": DispositionPolicy("busy", "no_stage_change", "record_attempt_and_retry", True, "policy_retry", "preserve", "Line busy", "odoo.disposition.busy.v1"),
    "NA": DispositionPolicy("no_answer", "no_stage_change", "record_attempt_and_retry", True, "policy_retry", "preserve", "No answer", "odoo.disposition.no_answer.v1"),
    "NI": DispositionPolicy("not_interested", "mark_not_interested", "close_open_call_activities", False, "clear", "preserve", "Contact not interested", "odoo.disposition.not_interested.v1"),
    "DNC": DispositionPolicy("do_not_call", "mark_do_not_contact", "close_open_call_activities", False, "clear", "set_and_suppress", "Do-not-call request", "odoo.disposition.dnc.v1"),
    "WRONG": DispositionPolicy("wrong_number", "no_stage_change", "close_phone_activities", False, "clear", "suppress_number", "Wrong number", "odoo.disposition.wrong_number.v1"),
    "DISCONNECTED": DispositionPolicy("disconnected", "no_stage_change", "close_phone_activities", False, "clear", "suppress_number", "Number disconnected", "odoo.disposition.disconnected.v1"),
    "ANSWERED": DispositionPolicy("answered", "no_stage_change", "record_completed_attempt", False, "none", "preserve", "Answered; no sale inferred", "odoo.disposition.answered.v1"),
    "TRANSFER": DispositionPolicy("transfer", "no_stage_change", "record_transfer_outcome", False, "none", "preserve", "Transfer destination and outcome required", "odoo.disposition.transfer.v1"),
    "APPOINTMENT": DispositionPolicy("appointment", "no_stage_change", "create_or_update_appointment", False, "appointment_datetime", "preserve", "Appointment details required", "odoo.disposition.appointment.v1"),
}

ALIASES = {"CB": "CALLBK", "WN": "WRONG", "DC": "DISCONNECTED", "XFER": "TRANSFER", "APPT": "APPOINTMENT"}


def disposition_policy(status: str) -> DispositionPolicy:
    canonical = ALIASES.get(status.strip().upper(), status.strip().upper())
    try:
        return POLICIES[canonical]
    except KeyError as exc:
        raise ValueError("unsupported VICIdial disposition") from exc
