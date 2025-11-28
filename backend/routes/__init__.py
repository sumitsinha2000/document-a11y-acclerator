"""FastAPI router modules for backend endpoints."""

from .health import router as health_router
from .groups import router as groups_router
from .folders import router as folders_router
from .scans import router as scans_router
from .fixes import router as fixes_router
from .debug_scans import router as debug_scans_router

__all__ = [
    "health_router",
    "groups_router",
    "folders_router",
    "scans_router",
    "fixes_router",
    "debug_scans_router",
]
