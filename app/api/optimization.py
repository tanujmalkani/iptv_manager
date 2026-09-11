from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.schemas import OptimizationPlanResponse
from app.db.models import (
    Channel,
    PlaylistEntry,
    SourcePlaylistVersion,
    Stream,
    StreamTest,
    StreamVariant,
)
from app.db.models.enums import VersionStatus
from app.db.session import get_db
from app.optimization import OptimizationProfile, build_optimization_plan

router = APIRouter(prefix="/api", tags=["optimization"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get(
    "/source-playlists/{source_playlist_id}/optimization",
    response_model=OptimizationPlanResponse,
)
def get_playlist_optimization(
    source_playlist_id: int,
    session: DbSession,
    profile: OptimizationProfile = OptimizationProfile.FAST,
) -> OptimizationPlanResponse:
    """Preview the ranked optimization plan for a playlist version."""
    version = session.scalar(
        select(SourcePlaylistVersion)
        .where(
            SourcePlaylistVersion.source_playlist_id == source_playlist_id,
            SourcePlaylistVersion.status == VersionStatus.COMPLETED.value,
        )
        .order_by(SourcePlaylistVersion.version_number.desc())
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Completed playlist version not found")

    rows = session.execute(
        select(PlaylistEntry.channel_id, PlaylistEntry.stream_id)
        .where(PlaylistEntry.source_playlist_version_id == version.id)
        .distinct()
    ).all()
    stream_ids_by_channel: dict[int, set[int]] = {}
    for channel_id, stream_id in rows:
        if stream_id is not None:
            stream_ids_by_channel.setdefault(channel_id, set()).add(stream_id)

    root_stream_ids = {stream_id for ids in stream_ids_by_channel.values() for stream_id in ids}
    discovered_ids_by_root = _load_discovered_stream_ids(session, root_stream_ids)
    for channel_id, root_ids in list(stream_ids_by_channel.items()):
        expanded = set(root_ids)
        for root_id in root_ids:
            expanded.update(discovered_ids_by_root.get(root_id, set()))
        stream_ids_by_channel[channel_id] = expanded

    channels = session.scalars(
        select(Channel)
        .options(selectinload(Channel.streams))
        .where(Channel.id.in_(stream_ids_by_channel))
        .order_by(Channel.canonical_name, Channel.id)
    ).all()

    stream_ids = {stream_id for ids in stream_ids_by_channel.values() for stream_id in ids}
    streams = (
        session.scalars(select(Stream).where(Stream.id.in_(stream_ids))).all()
        if stream_ids
        else []
    )
    playable_stream_ids = {
        stream.id for stream in streams if stream.stream_kind != "master_playlist"
    }
    stream_ids_by_channel = {
        channel_id: ids & playable_stream_ids
        for channel_id, ids in stream_ids_by_channel.items()
    }
    stream_ids = {stream_id for ids in stream_ids_by_channel.values() for stream_id in ids}

    tests_by_stream: dict[int, list[StreamTest]] = {stream_id: [] for stream_id in stream_ids}
    if stream_ids:
        tests = session.scalars(
            select(StreamTest)
            .where(StreamTest.stream_id.in_(stream_ids))
            .order_by(StreamTest.stream_id, StreamTest.completed_at, StreamTest.id)
        ).all()
        for test in tests:
            tests_by_stream.setdefault(test.stream_id, []).append(test)

    plan = build_optimization_plan(
        channels,
        tests_by_stream,
        stream_ids_by_channel,
        profile,
    )
    return OptimizationPlanResponse.from_model(plan, version.version_number)


def _load_discovered_stream_ids(
    session: Session,
    root_stream_ids: set[int],
) -> dict[int, set[int]]:
    """Return all recursively discovered descendant streams for each root stream."""
    descendants_by_root: dict[int, set[int]] = {
        root_id: set() for root_id in root_stream_ids
    }
    frontier = set(root_stream_ids)
    root_by_frontier: dict[int, set[int]] = {
        stream_id: {stream_id} for stream_id in root_stream_ids
    }

    while frontier:
        rows = session.execute(
            select(StreamVariant.parent_stream_id, StreamVariant.variant_stream_id).where(
                StreamVariant.parent_stream_id.in_(frontier)
            )
        ).all()
        next_frontier: set[int] = set()
        next_root_map: dict[int, set[int]] = {}
        for parent_id, child_id in rows:
            roots = root_by_frontier.get(parent_id, set())
            if not roots:
                continue
            for root_id in roots:
                if child_id in descendants_by_root[root_id]:
                    continue
                descendants_by_root[root_id].add(child_id)
                next_root_map.setdefault(child_id, set()).add(root_id)
            if child_id not in frontier:
                next_frontier.add(child_id)

        frontier = next_frontier
        root_by_frontier = next_root_map

    return descendants_by_root
