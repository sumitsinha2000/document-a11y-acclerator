"""FastAPI router modules for backend endpoints."""

from .health import router as health_router
from .projects import router as projects_router
from .folders import router as folders_router
from .scans import router as scans_router
from .fixes import router as fixes_router
from .debug_scans import router as debug_scans_router

__all__ = [
    "health_router",
    "projects_router",
    "folders_router",
    "scans_router",
    "fixes_router",
    "debug_scans_router",
]
