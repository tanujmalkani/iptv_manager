from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.exporter import export_optimized_m3u

router = APIRouter(prefix="/api", tags=["export"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/source-playlists/{source_playlist_id}/optimized.m3u")
def export_source_playlist(
    source_playlist_id: int,
    session: DbSession,
    version_id: int | None = None,
) -> PlainTextResponse:
    """Export the latest completed source playlist with proven primary streams."""
    result = export_optimized_m3u(session, source_playlist_id, version_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Completed playlist version not found")

    return PlainTextResponse(
        result.content,
        media_type="audio/x-mpegurl",
        headers={
            "Content-Disposition": (
                f'attachment; filename="iptv-manager-optimized-v{result.source_playlist_version_number}.m3u"'
            )
        },
    )
