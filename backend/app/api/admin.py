from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException, Query

from app.config import get_settings

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.api_route("/demo-reset", methods=["GET", "POST"], include_in_schema=False)
def demo_reset(
    authorization: str | None = Header(default=None),
    stale_hours: float | None = Query(default=None, ge=0, description="only reset if the data is older than this"),
) -> dict:
    """Public demo only: wipe all data and reload the sample documents.

    Authenticated with `Authorization: Bearer $CRON_SECRET` (a scheduler or the container's
    start-up seeder). The web proxy forwards that header only for this path, and the secret
    never leaves the server, so visitors cannot trigger it.
    """
    s = get_settings()
    if not s.demo_mode or not s.cron_secret:
        raise HTTPException(404, "Not found")
    if not authorization or not hmac.compare_digest(authorization, f"Bearer {s.cron_secret}"):
        raise HTTPException(401, "Unauthorized")
    from app.demo import data_age_hours, reset_and_seed

    if stale_hours is not None:
        age = data_age_hours()
        if age is not None and age < stale_hours:
            return {"skipped": True, "data_age_hours": round(age, 2)}
    return reset_and_seed()
