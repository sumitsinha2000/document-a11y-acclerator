"""FastAPI router modules for backend endpoints."""

from .health import router as health_router
from .groups import router as groups_router
from .scans import router as scans_router

__all__ = ["health_router", "groups_router", "scans_router"]
