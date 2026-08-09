from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.database import get_db
from app.models.user import User
from app.services.metrics import metrics_store
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/admin/metrics", tags=["Admin - Metrics"])


@router.get("/overview")
async def metrics_overview(
    hours: int = Query(default=2, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
) -> dict:
    """
    Live in-memory API metrics for the admin dashboard.

    Tracks aggregation volume, provider success/failure, and latency.
    Does not store search or booking payloads.
    """
    snapshot = metrics_store.snapshot(hours=hours)
    providers = await ProviderService(db).list_providers(enabled_only=False)
    enabled = sum(1 for p in providers if p.enabled)
    snapshot["configured_providers"] = len(providers)
    snapshot["enabled_providers"] = enabled
    return snapshot
