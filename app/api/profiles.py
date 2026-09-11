from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import PlaylistProfileRequest, PlaylistProfileResponse
from app.db.session import get_db
from app.profiles import (
    PlaylistProfileInput,
    ProfileEntryInput,
    create_profile,
    get_profile,
    list_profiles,
    update_profile,
)

router = APIRouter(prefix="/api/playlist-profiles", tags=["playlist-profiles"])
DbSession = Annotated[Session, Depends(get_db)]


def _input(data: PlaylistProfileRequest) -> PlaylistProfileInput:
    return PlaylistProfileInput(
        name=data.name,
        source_playlist_id=data.source_playlist_id,
        description=data.description,
        stream_mode=data.stream_mode,
        entries=tuple(
            ProfileEntryInput(
                channel_id=entry.channel_id,
                position=entry.position,
                enabled=entry.enabled,
                group_name=entry.group_name,
                selected_stream_id=entry.selected_stream_id,
            )
            for entry in data.entries
        ),
    )


@router.get("", response_model=list[PlaylistProfileResponse])
def list_playlist_profiles(
    session: DbSession,
    source_playlist_id: int | None = None,
) -> list[PlaylistProfileResponse]:
    return [
        PlaylistProfileResponse.from_model(item)
        for item in list_profiles(session, source_playlist_id)
    ]


@router.get("/{profile_id}", response_model=PlaylistProfileResponse)
def get_playlist_profile(profile_id: int, session: DbSession) -> PlaylistProfileResponse:
    profile = get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Playlist profile not found")
    return PlaylistProfileResponse.from_model(profile)


@router.post("", response_model=PlaylistProfileResponse, status_code=201)
def create_playlist_profile(
    data: PlaylistProfileRequest,
    session: DbSession,
) -> PlaylistProfileResponse:
    try:
        profile = create_profile(session, _input(data))
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlaylistProfileResponse.from_model(get_profile(session, profile.id))


@router.put("/{profile_id}", response_model=PlaylistProfileResponse)
def update_playlist_profile(
    profile_id: int,
    data: PlaylistProfileRequest,
    session: DbSession,
) -> PlaylistProfileResponse:
    profile = get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Playlist profile not found")
    try:
        profile = update_profile(session, profile, _input(data))
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlaylistProfileResponse.from_model(get_profile(session, profile.id))


@router.delete("/{profile_id}", status_code=204)
def delete_playlist_profile(profile_id: int, session: DbSession) -> None:
    profile = get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Playlist profile not found")
    session.delete(profile)
    session.commit()
