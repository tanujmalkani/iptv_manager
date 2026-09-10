from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import SourcePlaylistResponse
from app.db.models import SourcePlaylist, SourcePlaylistVersion
from app.db.models.enums import VersionStatus
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["playlists"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/source-playlists", response_model=list[SourcePlaylistResponse])
def list_source_playlists(session: DbSession) -> list[SourcePlaylistResponse]:
    """List imported playlists and their latest completed version."""
    playlists = session.scalars(select(SourcePlaylist).order_by(SourcePlaylist.name, SourcePlaylist.id)).all()
    versions = session.scalars(
        select(SourcePlaylistVersion)
        .where(SourcePlaylistVersion.status == VersionStatus.COMPLETED.value)
        .order_by(SourcePlaylistVersion.source_playlist_id, SourcePlaylistVersion.version_number.desc())
    ).all()

    latest_by_playlist: dict[int, SourcePlaylistVersion] = {}
    for version in versions:
        latest_by_playlist.setdefault(version.source_playlist_id, version)

    return [
        SourcePlaylistResponse.from_model(playlist, latest_by_playlist.get(playlist.id))
        for playlist in playlists
    ]
