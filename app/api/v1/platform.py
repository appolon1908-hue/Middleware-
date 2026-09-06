"""Canonical service catalog and review-gated provisioning workflow."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

router = APIRouter(prefix="/platform/v1", tags=["platform-service-catalog"])
SERVICE_ID = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
REPOSITORY = re.compile(r"^appolon1908-hue/[A-Za-z0-9._-]+$")
ENVIRONMENTS = {"development", "test", "staging", "production"}
ADMIN_ROLES = {"platform_admin", "platform_reviewer"}


class ServiceCreate(BaseModel):
    service_id: str
    owner: str = Field(min_length=2, max_length=128)
    tenant_mode: Literal["single-tenant", "multi-tenant", "platform"]
    type: Literal["api", "website", "worker", "adapter", "scheduled-job", "websocket"]
    repository: str
    environments: list[str]
    health_path: str = "/health/ready"
    metrics_path: str = "/metrics"
    openapi_path: str = "/openapi.json"
    dependencies: list[str] = Field(default_factory=list, max_length=64)
    data_classification: Literal["public", "internal", "confidential", "restricted"]
    slo_profile: str = Field(min_length=2, max_length=64)
    alert_profile: str = Field(min_length=2, max_length=64)

    @field_validator("service_id")
    @classmethod
    def service_id_is_safe(cls, value: str) -> str:
        if not SERVICE_ID.fullmatch(value):
            raise ValueError("service_id must be lowercase kebab-case")
        return value

    @field_validator("repository")
    @classmethod
    def repository_is_governed(cls, value: str) -> str:
        if not REPOSITORY.fullmatch(value):
            raise ValueError("repository must belong to appolon1908-hue")
        return value

    @field_validator("environments")
    @classmethod
    def environments_are_governed(cls, value: list[str]) -> list[str]:
        if not value or len(value) != len(set(value)) or not set(value) <= ENVIRONMENTS:
            raise ValueError("environments must be unique governed values")
        return value

    @field_validator("health_path", "metrics_path", "openapi_path")
    @classmethod
    def path_is_safe(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//") or "?" in value or "#" in value:
            raise ValueError("contract paths must be absolute and query-free")
        return value


class ServicePatch(BaseModel):
    owner: str | None = Field(default=None, min_length=2, max_length=128)
    dependencies: list[str] | None = Field(default=None, max_length=64)
    slo_profile: str | None = Field(default=None, min_length=2, max_length=64)
    alert_profile: str | None = Field(default=None, min_length=2, max_length=64)


class EnvironmentCreate(BaseModel):
    environment: Literal["development", "test", "staging", "production"]
    region: str = Field(pattern=r"^[a-z0-9-]{2,32}$")


class ProvisioningCreate(BaseModel):
    service_id: str
    environment: Literal["development", "test", "staging", "production"]
    manifest_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    git_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    requested_components: list[Literal["caddy", "kong", "keycloak", "openbao", "prometheus", "alertmanager", "loki", "tempo", "alloy", "grafana", "cicd"]]


class Transition(BaseModel):
    reason: str = Field(min_length=20, max_length=1000)


class CertificationSubmission(Transition):
    manifest_valid: bool
    openapi_valid: bool
    authorization_tests: bool
    tenant_isolation: bool
    secrets_externalized: bool
    health_endpoints: bool
    metrics_scraped: bool
    logs_received: bool
    traces_received: bool
    alert_route_test: bool
    image_digest_pinned: bool
    sbom_present: bool
    provenance_verified: bool
    rollback_verified: bool
    live_delivery_disabled: bool

    def evidence(self) -> dict[str, bool]:
        return self.model_dump(exclude={"reason"})


def require_role(role: str, allowed: set[str] = ADMIN_ROLES) -> None:
    if role not in allowed:
        raise HTTPException(403, "eligible platform role required")


def now() -> datetime:
    return datetime.now(timezone.utc)


def audit_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@router.post("/services", status_code=status.HTTP_201_CREATED)
async def create_service(body: ServiceCreate, db: AsyncSession = Depends(get_session)):
    service_uuid = uuid4()
    try:
        await db.execute(text("""INSERT INTO platform_services
          (id,service_id,owner,tenant_mode,service_type,repository,environments,health_path,metrics_path,openapi_path,dependencies,data_classification,slo_profile,alert_profile,state,created_at,updated_at)
          VALUES (:id,:service_id,:owner,:tenant_mode,:service_type,:repository,CAST(:environments AS jsonb),:health_path,:metrics_path,:openapi_path,CAST(:dependencies AS jsonb),:classification,:slo,:alert,'registered',:now,:now)"""), {
            "id": service_uuid, "service_id": body.service_id, "owner": body.owner,
            "tenant_mode": body.tenant_mode, "service_type": body.type, "repository": body.repository,
            "environments": json.dumps(body.environments), "health_path": body.health_path,
            "metrics_path": body.metrics_path, "openapi_path": body.openapi_path,
            "dependencies": json.dumps(body.dependencies), "classification": body.data_classification,
            "slo": body.slo_profile, "alert": body.alert_profile, "now": now(),
        })
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(409, "service_id or repository already registered") from exc
    return {"service_id": body.service_id, "state": "registered", "catalog_id": str(service_uuid)}


@router.get("/services")
async def list_services(db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(text("SELECT service_id,owner,tenant_mode,service_type,repository,environments,dependencies,data_classification,slo_profile,alert_profile,state,updated_at FROM platform_services ORDER BY service_id"))).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/services/{service_id}")
async def get_service(service_id: str, db: AsyncSession = Depends(get_session)):
    row = (await db.execute(text("SELECT * FROM platform_services WHERE service_id=:id"), {"id": service_id})).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "service not found")
    result = dict(row)
    result.pop("id", None)
    return result


@router.patch("/services/{service_id}")
async def patch_service(service_id: str, body: ServicePatch, db: AsyncSession = Depends(get_session)):
    changes = body.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(400, "at least one change is required")
    current = await get_service(service_id, db)
    merged = {**current, **changes}
    result = await db.execute(text("""UPDATE platform_services SET owner=:owner,dependencies=CAST(:dependencies AS jsonb),slo_profile=:slo,alert_profile=:alert,updated_at=:now WHERE service_id=:id RETURNING id"""), {"owner": merged["owner"], "dependencies": json.dumps(merged["dependencies"]), "slo": merged["slo_profile"], "alert": merged["alert_profile"], "now": now(), "id": service_id})
    updated = result.scalar_one_or_none()
    await db.commit()
    if updated is None:
        raise HTTPException(404, "service not found")
    return {"service_id": service_id, "state": current["state"]}


@router.post("/services/{service_id}/environments", status_code=201)
async def add_environment(service_id: str, body: EnvironmentCreate, db: AsyncSession = Depends(get_session)):
    service = await get_service(service_id, db)
    if body.environment not in service["environments"]:
        raise HTTPException(409, "environment is not declared by the service")
    await db.execute(text("INSERT INTO platform_service_environments(id,service_id,environment,region,state,created_at) SELECT :uuid,id,:env,:region,'declared',:now FROM platform_services WHERE service_id=:id ON CONFLICT(service_id,environment,region) DO NOTHING"), {"uuid": uuid4(), "env": body.environment, "region": body.region, "now": now(), "id": service_id})
    await db.commit()
    return {"service_id": service_id, "environment": body.environment, "region": body.region, "state": "declared"}


async def service_state(service_id: str, target: str, role: str, db: AsyncSession):
    require_role(role, {"platform_admin"})
    result = await db.execute(text("UPDATE platform_services SET state=:state,updated_at=:now WHERE service_id=:id RETURNING id"), {"state": target, "now": now(), "id": service_id})
    updated = result.scalar_one_or_none()
    await db.commit()
    if updated is None:
        raise HTTPException(404, "service not found")
    return {"service_id": service_id, "state": target}


@router.post("/services/{service_id}/activate")
async def activate_service(service_id: str, x_codestra_role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)):
    return await service_state(service_id, "active", x_codestra_role, db)


@router.post("/services/{service_id}/decommission")
async def decommission_service(service_id: str, x_codestra_role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)):
    return await service_state(service_id, "decommissioned", x_codestra_role, db)


@router.post("/provisioning/requests", status_code=202)
async def create_provisioning(body: ProvisioningCreate, x_correlation_id: str = Header("", alias="X-Correlation-ID"), db: AsyncSession = Depends(get_session)):
    request_id = uuid4()
    await get_service(body.service_id, db)
    payload = body.model_dump(mode="json")
    await db.execute(text("""INSERT INTO platform_provisioning_requests(id,service_id,environment,state,request_json,manifest_sha256,git_sha,correlation_id,created_at,updated_at)
      SELECT :uuid,id,:env,'requested',CAST(:request AS jsonb),:manifest,:git,:correlation,:now,:now FROM platform_services WHERE service_id=:service_id"""), {"uuid": request_id, "service_id": body.service_id, "env": body.environment, "request": json.dumps(payload), "manifest": body.manifest_sha256, "git": body.git_sha, "correlation": x_correlation_id or str(request_id), "now": now()})
    await db.commit()
    return {"request_id": str(request_id), "state": "requested", "apply_authorized": False}


@router.get("/provisioning/requests/{request_id}")
async def get_provisioning(request_id: UUID, db: AsyncSession = Depends(get_session)):
    row = (await db.execute(text("SELECT id,environment,state,request_json,manifest_sha256,git_sha,correlation_id,validation_json,approved_by,created_at,updated_at FROM platform_provisioning_requests WHERE id=:id"), {"id": request_id})).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "provisioning request not found")
    return dict(row)


async def transition(request_id: UUID, allowed: set[str], target: str, body: Transition, role: str, db: AsyncSession, validation: dict[str, bool] | None = None):
    require_role(role, {"platform_admin"} if target in {"apply_requested", "rollback_requested"} else ADMIN_ROLES)
    current = await get_provisioning(request_id, db)
    if current["state"] not in allowed:
        raise HTTPException(409, f"cannot transition {current['state']} to {target}")
    evidence = validation if validation is not None else current.get("validation_json")
    await db.execute(text("UPDATE platform_provisioning_requests SET state=:state,validation_json=CAST(:validation AS jsonb),approved_by=CASE WHEN :state='approved' THEN :role ELSE approved_by END,updated_at=:now WHERE id=:id"), {"state": target, "validation": json.dumps(evidence), "role": role, "now": now(), "id": request_id})
    await db.execute(text("INSERT INTO platform_provisioning_audit(id,request_id,from_state,to_state,actor_role,reason,record_hash,created_at) VALUES (:id,:request,:from_state,:to_state,:actor,:reason,:hash,:now)"), {"id": uuid4(), "request": request_id, "from_state": current["state"], "to_state": target, "actor": role, "reason": body.reason, "hash": audit_hash({"id": str(request_id), "from": current["state"], "to": target, "role": role, "reason": body.reason}), "now": now()})
    await db.commit()
    return {"request_id": str(request_id), "state": target, "apply_authorized": False}


@router.post("/provisioning/requests/{request_id}/validate")
async def validate_provisioning(request_id: UUID, body: CertificationSubmission, role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)):
    evidence = body.evidence()
    failed = sorted(name for name, passed in evidence.items() if not passed)
    if failed:
        raise HTTPException(422, {"message": "certification gates failed", "failed_gates": failed})
    return await transition(request_id, {"requested"}, "validated", body, role, db, evidence)


@router.post("/provisioning/requests/{request_id}/approve")
async def approve_provisioning(request_id: UUID, body: Transition, role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)):
    return await transition(request_id, {"validated"}, "approved", body, role, db)


@router.post("/provisioning/requests/{request_id}/apply")
async def apply_provisioning(request_id: UUID, body: Transition, role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)):
    return await transition(request_id, {"approved"}, "apply_requested", body, role, db)


@router.post("/provisioning/requests/{request_id}/rollback")
async def rollback_provisioning(request_id: UUID, body: Transition, role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)):
    return await transition(request_id, {"applied", "failed"}, "rollback_requested", body, role, db)
