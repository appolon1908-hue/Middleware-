"""Codestra Middleware application package and deterministic route registry."""

from importlib.util import find_spec

__all__ = ["create_app"]


# Some source-only governance validators intentionally import lightweight app
# modules before web dependencies are installed. Register provider-control
# routes whenever the actual FastAPI runtime is available; dependency-light
# validators remain importable without weakening runtime route registration.
if find_spec("fastapi") is not None:
    from . import provider_control_api as _provider_control_api  # noqa: F401,E402


def __getattr__(name: str):
    if name == "create_app":
        from .main import create_app

        return create_app
    raise AttributeError(name)
