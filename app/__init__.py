"""Codestra Middleware application package and deterministic route registry."""

__all__ = ["create_app"]


# Provider-control routes extend the durable control router before app.main
# includes it. Importing this module has no runtime effect beyond deterministic
# route registration from the checked-in provider-operation policy.
from . import provider_control_api as _provider_control_api  # noqa: F401,E402


def __getattr__(name: str):
    if name == "create_app":
        from .main import create_app

        return create_app
    raise AttributeError(name)
