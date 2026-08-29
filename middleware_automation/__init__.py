"""Middleware automation control-plane implementation."""

from .service import AutomationService, AutomationError

__all__ = ["AutomationService", "AutomationError"]
