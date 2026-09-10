"""Monitoring authority comes from the original verified JWT, never headers."""

from __future__ import annotations

from dataclasses import dataclass
import re

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.jwt_auth import JWTAuthError, KeycloakValidator

bearer = HTTPBearer(auto_error=False)
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
READ_ROLES = frozenset({"platform_admin", "platform_operator", "platform_reviewer"})


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant: str
    roles: frozenset[str]
    campaigns: frozenset[str]
    services: frozenset[str]
    client: str

    def check_campaign(self, campaign: str | None):
        if "campaign_supervisor" in self.roles and not self.roles.intersection(
            READ_ROLES
        ):
            if campaign is not None and campaign not in self.campaigns:
                raise HTTPException(403, "campaign authority denied")


def require(scope: str, roles: frozenset[str] = READ_ROLES):
    def authorize(
        credential: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> Principal:
        if credential is None or credential.scheme.lower() != "bearer":
            raise HTTPException(
                401,
                "verified monitoring bearer required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        parties = frozenset(
            x.strip()
            for x in settings.keycloak_authorized_parties.split(",")
            if x.strip()
        )
        if not all(
            (
                parties,
                settings.keycloak_issuer,
                settings.keycloak_audience,
                settings.keycloak_jwks_url,
            )
        ):
            raise HTTPException(503, "monitoring identity authority is not configured")
        try:
            claims = KeycloakValidator(
                issuer=settings.keycloak_issuer,
                audience=settings.keycloak_audience,
                jwks_url=settings.keycloak_jwks_url,
                authorized_parties=parties,
                required_scopes=frozenset({scope}),
            ).validate(credential.credentials)
            subject, tenant = claims.get("sub"), claims.get("tenant_id")
            raw_roles = claims.get("realm_access", {}).get("roles", [])
            campaigns, services = (
                claims.get("campaigns", []),
                claims.get("services", []),
            )
            if (
                not isinstance(subject, str)
                or not subject.strip()
                or len(subject) > 255
            ):
                raise JWTAuthError("subject")
            if not isinstance(tenant, str) or not ID.fullmatch(tenant):
                raise JWTAuthError("tenant")
            if not isinstance(claims.get("scope"), str):
                raise JWTAuthError("scope")
            for collection in (raw_roles, campaigns, services):
                if not isinstance(collection, list) or not all(
                    isinstance(v, str) and ID.fullmatch(v) for v in collection
                ):
                    raise JWTAuthError("claims")
            if not roles.intersection(raw_roles):
                raise JWTAuthError("role")
            return Principal(
                subject,
                tenant,
                frozenset(raw_roles),
                frozenset(campaigns),
                frozenset(services),
                claims["azp"],
            )
        except (JWTAuthError, ValueError, TypeError, AttributeError):
            raise HTTPException(403, "monitoring authority denied") from None

    return authorize
