"""Health and diagnostics routes."""

from fastapi import APIRouter

from backend.utils.app_helpers import FIXED_FOLDER, UPLOAD_FOLDER

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Return basic service/ storage health information."""
    return {"status": "ok", "uploads": UPLOAD_FOLDER, "fixed": FIXED_FOLDER}
