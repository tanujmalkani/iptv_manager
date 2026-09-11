from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    PlaylistEntry,
    PlaylistProfile,
    PlaylistProfileEntry,
    PlaylistProfileGroup,
    SourcePlaylistVersion,
    Stream,
)
from app.db.models.enums import VersionStatus
from app.optimization import OptimizationProfile


@dataclass(frozen=True, slots=True)
class ProfileEntryInput:
    channel_id: int
    position: int
    enabled: bool = True
    group_name: str | None = None
    selected_stream_id: int | None = None


@dataclass(frozen=True, slots=True)
class PlaylistProfileInput:
    name: str
    source_playlist_id: int
    description: str | None
    stream_mode: str
    entries: tuple[ProfileEntryInput, ...]


def list_profiles(session: Session, source_playlist_id: int | None = None) -> list[PlaylistProfile]:
    statement = (
        select(PlaylistProfile)
        .options(selectinload(PlaylistProfile.entries).selectinload(PlaylistProfileEntry.channel))
        .order_by(PlaylistProfile.name, PlaylistProfile.id)
    )
    if source_playlist_id is not None:
        statement = statement.where(PlaylistProfile.source_playlist_id == source_playlist_id)
    return session.scalars(statement).unique().all()


def get_profile(session: Session, profile_id: int) -> PlaylistProfile | None:
    return session.scalar(
        select(PlaylistProfile)
        .options(
            selectinload(PlaylistProfile.entries).selectinload(PlaylistProfileEntry.channel),
            selectinload(PlaylistProfile.groups),
        )
        .where(PlaylistProfile.id == profile_id)
    )


def create_profile(session: Session, data: PlaylistProfileInput) -> PlaylistProfile:
    _validate_entries(session, data.source_playlist_id, data.entries)
    _validate_stream_mode(data.stream_mode)
    profile = PlaylistProfile(
        source_playlist_id=data.source_playlist_id,
        name=data.name.strip(),
        description=data.description.strip() if data.description else None,
        selection_mode="custom",
        stream_mode=data.stream_mode,
    )
    session.add(profile)
    session.flush()
    _replace_entries(session, profile, data.entries)
    session.flush()
    return profile


def update_profile(
    session: Session,
    profile: PlaylistProfile,
    data: PlaylistProfileInput,
) -> PlaylistProfile:
    _validate_entries(session, data.source_playlist_id, data.entries)
    _validate_stream_mode(data.stream_mode)
    profile.source_playlist_id = data.source_playlist_id
    profile.name = data.name.strip()
    profile.description = data.description.strip() if data.description else None
    profile.stream_mode = data.stream_mode
    _replace_entries(session, profile, data.entries)
    session.flush()
    return profile


def _validate_stream_mode(stream_mode: str) -> None:
    valid = {"source", *(item.value for item in OptimizationProfile)}
    if stream_mode not in valid:
        raise ValueError(f"Unsupported stream mode: {stream_mode}")


def _validate_entries(
    session: Session,
    source_playlist_id: int,
    entries: tuple[ProfileEntryInput, ...],
) -> None:
    positions = [entry.position for entry in entries]
    if positions != list(range(len(entries))):
        raise ValueError("Profile positions must be consecutive starting at zero")
    channel_ids = [entry.channel_id for entry in entries]
    if len(channel_ids) != len(set(channel_ids)):
        raise ValueError("A channel may appear only once in a profile")

    latest_version = session.scalar(
        select(SourcePlaylistVersion)
        .where(
            SourcePlaylistVersion.source_playlist_id == source_playlist_id,
            SourcePlaylistVersion.status == VersionStatus.COMPLETED.value,
        )
        .order_by(SourcePlaylistVersion.version_number.desc())
        .limit(1)
    )
    if latest_version is None:
        raise ValueError("Completed playlist version not found")

    available = set(
        session.scalars(
            select(PlaylistEntry.channel_id)
            .where(PlaylistEntry.source_playlist_version_id == latest_version.id)
            .distinct()
        ).all()
    )
    missing = set(channel_ids) - available
    if missing:
        raise ValueError("Profile contains channels that are not in the source playlist")

    selected_pairs = {
        (entry.channel_id, entry.selected_stream_id)
        for entry in entries
        if entry.selected_stream_id is not None
    }
    if selected_pairs:
        valid_pairs = set(
            session.execute(
                select(PlaylistEntry.channel_id, PlaylistEntry.stream_id)
                .join(Stream, Stream.id == PlaylistEntry.stream_id)
                .where(
                    PlaylistEntry.source_playlist_version_id == latest_version.id,
                    PlaylistEntry.channel_id.in_(channel_ids),
                    Stream.stream_kind != "master_playlist",
                )
                .distinct()
            ).all()
        )
        if selected_pairs - valid_pairs:
            raise ValueError(
                "Profile contains a stream that is not a playable option for its channel"
            )


def _replace_entries(
    session: Session,
    profile: PlaylistProfile,
    entries: tuple[ProfileEntryInput, ...],
) -> None:
    for entry in list(profile.entries):
        session.delete(entry)
    session.flush()

    for group in list(profile.groups):
        session.delete(group)
    session.flush()

    groups: dict[str, PlaylistProfileGroup] = {}
    for entry in entries:
        group = None
        if entry.group_name:
            group = groups.get(entry.group_name)
            if group is None:
                group = PlaylistProfileGroup(profile_id=profile.id, name=entry.group_name)
                session.add(group)
                groups[entry.group_name] = group
        session.add(
            PlaylistProfileEntry(
                profile_id=profile.id,
                channel_id=entry.channel_id,
                group=group,
                position=entry.position,
                enabled=entry.enabled,
                selected_stream_id=entry.selected_stream_id,
            )
        )
