from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import SourcePlaylistResponse
from app.db.models import SourcePlaylist, SourcePlaylistVersion
from app.db.models.enums import VersionStatus
from app.db.session import get_db
from app.importer.job import get_import_job, serialize_import_job, start_import_job

router = APIRouter(prefix="/api", tags=["playlists"])
DbSession = Annotated[Session, Depends(get_db)]


class PlaylistImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1)
    source_location: str | None = Field(default=None, max_length=2000)


@router.get("/source-playlists", response_model=list[SourcePlaylistResponse])
def list_source_playlists(session: DbSession) -> list[SourcePlaylistResponse]:
    """List imported playlists and their latest completed version."""
    playlists = session.scalars(
        select(SourcePlaylist).order_by(SourcePlaylist.name, SourcePlaylist.id)
    ).all()
    versions = session.scalars(
        select(SourcePlaylistVersion)
        .where(SourcePlaylistVersion.status == VersionStatus.COMPLETED.value)
        .order_by(
            SourcePlaylistVersion.source_playlist_id,
            SourcePlaylistVersion.version_number.desc(),
        )
    ).all()

    latest_by_playlist: dict[int, SourcePlaylistVersion] = {}
    for version in versions:
        latest_by_playlist.setdefault(version.source_playlist_id, version)

    return [
        SourcePlaylistResponse.from_model(playlist, latest_by_playlist.get(playlist.id))
        for playlist in playlists
    ]


@router.post("/source-playlists/import")
def import_playlist(payload: PlaylistImportRequest) -> dict[str, object]:
    """Start importing M3U content in the background and return a job id."""
    job = start_import_job(
        name=payload.name.strip(),
        text=payload.text,
        source_location=payload.source_location.strip() if payload.source_location else None,
    )
    return {"import_id": job.id, "status": job.status}


@router.get("/source-playlists/import/{import_id}")
def get_import_status(import_id: str) -> dict[str, object]:
    """Return current background playlist import progress and result."""
    job = get_import_job(import_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return serialize_import_job(job)
