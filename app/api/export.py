from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.exporter import export_m3u, export_optimized_m3u
from app.optimization import OptimizationProfile

router = APIRouter(prefix="/api", tags=["export"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/source-playlists/{source_playlist_id}/export.m3u")
def export_source_playlist(
    source_playlist_id: int,
    session: DbSession,
    optimization_profile: OptimizationProfile | None = None,
    playlist_profile_id: int | None = None,
    version_id: int | None = None,
) -> PlainTextResponse:
    """Export an original or custom playlist with optional optimization."""
    result = export_m3u(
        session,
        source_playlist_id,
        version_id=version_id,
        optimization_profile=optimization_profile,
        playlist_profile_id=playlist_profile_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Playlist or completed version not found")

    parts = ["iptv-manager"]
    if playlist_profile_id is not None:
        parts.append(f"profile-{playlist_profile_id}")
    parts.append(optimization_profile.value if optimization_profile else "original")
    filename = f"{'-'.join(parts)}-v{result.source_playlist_version_number}.m3u"
    return PlainTextResponse(
        result.content,
        media_type="audio/x-mpegurl",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/source-playlists/{source_playlist_id}/optimized.m3u")
def export_optimized_playlist(
    source_playlist_id: int,
    session: DbSession,
    version_id: int | None = None,
) -> PlainTextResponse:
    """Backward-compatible Fast optimization export."""
    result = export_optimized_m3u(session, source_playlist_id, version_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Completed playlist version not found")
    filename = f"iptv-manager-optimized-v{result.source_playlist_version_number}.m3u"
    return PlainTextResponse(
        result.content,
        media_type="audio/x-mpegurl",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
