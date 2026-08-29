"""Durable-ish automation control-plane core for local and staging adapters.

The default store is in memory so unit tests and dry-run staging can execute
without touching production databases. Production wiring should provide a
transactional repository with the same service semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from .adapters import adapter_for


TERMINAL_JOB_STATES = {"COMPLETED", "FAILED"}
TERMINAL_COMMAND_STATES = {"SUCCEEDED", "FAILED", "REJECTED"}


COMMAND_PREFIXES: dict[str, dict[str, str]] = {
    "identity.": {"scope": "automation.command.identity", "client": "n8n-identity-automation"},
    "provisioning.": {"scope": "automation.command.identity", "client": "n8n-identity-automation"},
    "crm.": {"scope": "automation.command.crm", "client": "n8n-crm-automation"},
    "support.": {"scope": "automation.command.crm", "client": "n8n-crm-automation"},
    "telephony.": {"scope": "automation.command.telephony", "client": "n8n-telephony-automation"},
    "email.": {"scope": "automation.command.messaging", "client": "n8n-messaging-automation"},
    "sms.": {"scope": "automation.command.messaging", "client": "n8n-messaging-automation"},
    "social.": {"scope": "automation.command.social", "client": "n8n-social-automation"},
    "crawler.": {"scope": "automation.command.crawler", "client": "n8n-crawler-automation"},
    "moneybee.": {"scope": "automation.command.product", "client": "n8n-product-automation"},
    "breero.": {"scope": "automation.command.product", "client": "n8n-product-automation"},
    "larim.": {"scope": "automation.command.product", "client": "n8n-product-automation"},
    "freight.": {"scope": "automation.command.product", "client": "n8n-product-automation"},
    "beyvra.operations.": {"scope": "automation.command.product", "client": "n8n-product-automation"},
    "booked4seasons.": {"scope": "automation.command.product", "client": "n8n-product-automation"},
    "trading.operations.": {"scope": "automation.command.product", "client": "n8n-product-automation"},
    "real-wallet.operations.": {"scope": "automation.command.product", "client": "n8n-product-automation"},
    "privacy.": {"scope": "automation.command.privacy", "client": "n8n-privacy-automation"},
}


@dataclass
class AutomationError(Exception):
    status: int
    code: str
    message: str

    def body(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message}


@dataclass
class Job:
    job_id: str
    tenant_id: str
    actor_id: str
    workflow_key: str
    workflow_version: str
    delivery_token: str
    workflow_family: str
    state: str = "PENDING"
    attempts: int = 0
    lease_token: str | None = None
    execution_id: str | None = None
    leased_until: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None


class AutomationService:
    def __init__(self, now: Any | None = None, state_path: str | Path | None = None) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._state_path = Path(state_path) if state_path else None
        self.jobs: dict[str, Job] = {}
        self.commands: dict[str, dict[str, Any]] = {}
        self.command_by_idempotency: dict[str, str] = {}
        self.dead_letters: dict[str, dict[str, Any]] = {}
        self.reconciliation_runs: dict[str, dict[str, Any]] = {}
        self._load_state()

    def seed_job(
        self,
        *,
        job_id: str,
        tenant_id: str,
        actor_id: str,
        workflow_key: str,
        workflow_version: str,
        delivery_token: str,
        workflow_family: str,
    ) -> dict[str, Any]:
        for field_name, value in {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "workflow_key": workflow_key,
            "workflow_version": workflow_version,
            "delivery_token": delivery_token,
            "workflow_family": workflow_family,
        }.items():
            if not isinstance(value, str) or not value:
                raise AutomationError(400, "MISSING_FIELD", f"{field_name} is required")
        if job_id in self.jobs:
            raise AutomationError(409, "JOB_EXISTS", "job already exists")
        job = Job(
            job_id=job_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            workflow_key=workflow_key,
            workflow_version=workflow_version,
            delivery_token=delivery_token,
            workflow_family=workflow_family,
        )
        self.jobs[job_id] = job
        self._persist()
        return self._job_body(job)

    def claim_job(self, body: dict[str, Any]) -> dict[str, Any]:
        for field_name in ("job_id", "delivery_token", "workflow_key", "workflow_version", "execution_id"):
            self._require_string(body, field_name)
        job = self._job(body["job_id"])
        if job.state in TERMINAL_JOB_STATES:
            raise AutomationError(409, "JOB_TERMINAL", "terminal jobs cannot be claimed")
        if body["delivery_token"] != job.delivery_token:
            raise AutomationError(403, "BAD_DELIVERY_TOKEN", "delivery token does not match")
        if body["workflow_key"] != job.workflow_key or str(body["workflow_version"]) != job.workflow_version:
            raise AutomationError(409, "WORKFLOW_MISMATCH", "workflow identity does not match job")
        job.state = "CLAIMED"
        job.attempts += 1
        job.execution_id = body["execution_id"]
        job.lease_token = self._token("lease", job.job_id, body["execution_id"], str(job.attempts))
        job.leased_until = self._iso(self._now() + timedelta(minutes=5))
        self._persist()
        return {
            "job_id": job.job_id,
            "tenant_id": job.tenant_id,
            "actor_id": job.actor_id,
            "workflow_key": job.workflow_key,
            "workflow_version": job.workflow_version,
            "workflow_family": job.workflow_family,
            "state": job.state,
            "lease_token": job.lease_token,
            "leased_until": job.leased_until,
        }

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._job_body(self._job(job_id))

    def heartbeat_job(self, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
        job = self._leased_job(job_id, body)
        job.leased_until = self._iso(self._now() + timedelta(minutes=5))
        self._persist()
        return {"job_id": job.job_id, "state": job.state, "leased_until": job.leased_until}

    def record_step(self, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
        job = self._leased_job(job_id, body)
        for field_name in ("step_key", "status"):
            self._require_string(body, field_name)
        step = {
            "step_key": body["step_key"],
            "status": body["status"],
            "execution_id": body["execution_id"],
            "recorded_at": self._iso(self._now()),
            "data": body.get("data", {}),
        }
        job.steps.append(step)
        self._persist()
        return {"job_id": job.job_id, "step": step}

    def complete_job(self, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
        job = self._leased_job(job_id, body)
        job.state = "COMPLETED"
        job.result = {"completed_at": self._iso(self._now()), "result": body.get("result", {})}
        self._persist()
        return self._job_body(job)

    def fail_job(self, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
        job = self._leased_job(job_id, body)
        job.state = "FAILED"
        job.failure = {"failed_at": self._iso(self._now()), "error": body.get("error", {})}
        dead_letter_id = self._token("dlq", job.job_id, job.execution_id or "unknown")
        self.dead_letters[dead_letter_id] = {
            "dead_letter_id": dead_letter_id,
            "job_id": job.job_id,
            "tenant_id": job.tenant_id,
            "workflow_key": job.workflow_key,
            "workflow_version": job.workflow_version,
            "state": "OPEN",
            "safe_replay": bool(body.get("safe_replay", False)),
            "created_at": self._iso(self._now()),
            "error": body.get("error", {}),
            "version": 1,
        }
        response = self._job_body(job)
        response["dead_letter_id"] = dead_letter_id
        self._persist()
        return response

    def submit_command(self, body: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        if not idempotency_key:
            raise AutomationError(400, "MISSING_IDEMPOTENCY_KEY", "Idempotency-Key header is required")
        required = (
            "job_id",
            "lease_token",
            "execution_id",
            "workflow_key",
            "workflow_version",
            "step_key",
            "command_type",
        )
        for field_name in required:
            self._require_string(body, field_name)
        job = self._leased_job(body["job_id"], body)
        if body["workflow_key"] != job.workflow_key or str(body["workflow_version"]) != job.workflow_version:
            raise AutomationError(409, "WORKFLOW_MISMATCH", "command workflow identity does not match job")
        route = self._command_route(body["command_type"])
        fingerprint = self._fingerprint(body)
        if idempotency_key in self.command_by_idempotency:
            command_id = self.command_by_idempotency[idempotency_key]
            existing = self.commands[command_id]
            if existing["fingerprint"] != fingerprint:
                raise AutomationError(409, "IDEMPOTENCY_CONFLICT", "idempotency key was reused with different command content")
            return existing

        command_id = self._token("cmd", idempotency_key)
        dry_run = body.get("dry_run", True) is not False
        state = "DRY_RUN_ACCEPTED" if dry_run else "PENDING_ADAPTER"
        command = {
            "command_id": command_id,
            "idempotency_key": idempotency_key,
            "fingerprint": fingerprint,
            "job_id": job.job_id,
            "tenant_id": job.tenant_id,
            "actor_id": job.actor_id,
            "workflow_key": job.workflow_key,
            "workflow_version": job.workflow_version,
            "step_key": body["step_key"],
            "execution_id": body["execution_id"],
            "command_type": body["command_type"],
            "scope": route["scope"],
            "client": route["client"],
            "state": state,
            "dry_run": dry_run,
            "payload": body.get("payload", {}),
            "created_at": self._iso(self._now()),
            "adapter_result": self._adapter_result(body["command_type"], body.get("payload", {}), dry_run),
        }
        self.commands[command_id] = command
        self.command_by_idempotency[idempotency_key] = command_id
        self._persist()
        return command

    def get_command(self, command_id: str) -> dict[str, Any]:
        try:
            return self.commands[command_id]
        except KeyError as exc:
            raise AutomationError(404, "COMMAND_NOT_FOUND", "command does not exist") from exc

    def replay_dead_letter(self, dead_letter_id: str, body: dict[str, Any]) -> dict[str, Any]:
        dlq = self._dead_letter(dead_letter_id)
        if not dlq["safe_replay"]:
            raise AutomationError(409, "UNSAFE_REPLAY", "dead letter is not marked safe for replay")
        if body.get("expected_version") != dlq["version"]:
            raise AutomationError(409, "STALE_DEAD_LETTER", "dead letter version does not match")
        self._require_string(body, "reason")
        replay_job_id = self._token("job", dead_letter_id, str(dlq["version"]))
        replay = self.seed_job(
            job_id=replay_job_id,
            tenant_id=dlq["tenant_id"],
            actor_id="operations-replay",
            workflow_key=dlq["workflow_key"],
            workflow_version=dlq["workflow_version"],
            delivery_token=self._token("delivery", replay_job_id),
            workflow_family="operations.replay",
        )
        dlq["state"] = "REPLAY_REQUESTED"
        dlq["version"] += 1
        dlq["replay_reason"] = body["reason"]
        self._persist()
        return {"dead_letter_id": dead_letter_id, "state": dlq["state"], "replay_job": replay}

    def reconcile_jobs(self, body: dict[str, Any]) -> dict[str, Any]:
        run_id = self._token("reconcile", str(len(self.reconciliation_runs) + 1), self._iso(self._now()))
        unknown_commands = [
            command
            for command in self.commands.values()
            if command["state"] == "PENDING_ADAPTER"
        ]
        run = {
            "reconciliation_run_id": run_id,
            "state": "COMPLETED",
            "requested_by": body.get("requested_by", "unknown"),
            "checked_commands": len(unknown_commands),
            "created_at": self._iso(self._now()),
        }
        self.reconciliation_runs[run_id] = run
        self._persist()
        return run

    def capability(self, capability: str) -> dict[str, Any]:
        return {"capability": capability, "enabled": False, "mode": "STAGING_OFF"}

    def _leased_job(self, job_id: str, body: dict[str, Any]) -> Job:
        for field_name in ("lease_token", "execution_id"):
            self._require_string(body, field_name)
        job = self._job(job_id)
        if job.state != "CLAIMED":
            raise AutomationError(409, "JOB_NOT_CLAIMED", "job must be claimed first")
        if body["lease_token"] != job.lease_token or body["execution_id"] != job.execution_id:
            raise AutomationError(403, "LEASE_MISMATCH", "lease identity does not match")
        return job

    def _job(self, job_id: str) -> Job:
        try:
            return self.jobs[job_id]
        except KeyError as exc:
            raise AutomationError(404, "JOB_NOT_FOUND", "job does not exist") from exc

    def _dead_letter(self, dead_letter_id: str) -> dict[str, Any]:
        try:
            return self.dead_letters[dead_letter_id]
        except KeyError as exc:
            raise AutomationError(404, "DEAD_LETTER_NOT_FOUND", "dead letter does not exist") from exc

    def _command_route(self, command_type: str) -> dict[str, str]:
        for prefix, route in COMMAND_PREFIXES.items():
            if command_type.startswith(prefix):
                return route
        raise AutomationError(403, "COMMAND_PREFIX_DENIED", "command type is not allowed")

    def _adapter_result(self, command_type: str, payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
        adapter = adapter_for(command_type)
        if adapter is None:
            raise AutomationError(403, "ADAPTER_NOT_FOUND", "no adapter owns this command type")
        return adapter.execute(command_type, payload, dry_run=dry_run)

    def _job_body(self, job: Job) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "tenant_id": job.tenant_id,
            "actor_id": job.actor_id,
            "workflow_key": job.workflow_key,
            "workflow_version": job.workflow_version,
            "workflow_family": job.workflow_family,
            "state": job.state,
            "attempts": job.attempts,
            "lease_token": job.lease_token,
            "execution_id": job.execution_id,
            "leased_until": job.leased_until,
            "steps": job.steps,
            "result": job.result,
            "failure": job.failure,
        }

    def _load_state(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        data = json.loads(self._state_path.read_text(encoding="utf-8"))
        self.jobs = {
            job_id: Job(**job)
            for job_id, job in data.get("jobs", {}).items()
        }
        self.commands = data.get("commands", {})
        self.command_by_idempotency = data.get("command_by_idempotency", {})
        self.dead_letters = data.get("dead_letters", {})
        self.reconciliation_runs = data.get("reconciliation_runs", {})

    def _persist(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "jobs": {job_id: self._job_body(job) | {"delivery_token": job.delivery_token} for job_id, job in self.jobs.items()},
            "commands": self.commands,
            "command_by_idempotency": self.command_by_idempotency,
            "dead_letters": self.dead_letters,
            "reconciliation_runs": self.reconciliation_runs,
        }
        temp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        temp.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, self._state_path)

    @staticmethod
    def _require_string(body: dict[str, Any], field_name: str) -> None:
        if not isinstance(body.get(field_name), str) or not body[field_name]:
            raise AutomationError(400, "MISSING_FIELD", f"{field_name} is required")

    @staticmethod
    def _fingerprint(body: dict[str, Any]) -> str:
        import json

        return sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _token(*parts: str) -> str:
        if not parts:
            return uuid4().hex
        return sha256(":".join(parts).encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
