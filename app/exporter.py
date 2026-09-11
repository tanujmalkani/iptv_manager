from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Channel, PlaylistEntry, PlaylistProfile, SourcePlaylistVersion, Stream, StreamTest
from app.db.models.enums import VersionStatus
from app.optimization import OptimizationProfile, build_optimization_plan


@dataclass(frozen=True, slots=True)
class ExportResult:
    content: str
    source_playlist_version_id: int
    source_playlist_version_number: int
    channel_count: int
    optimized_count: int
    fallback_count: int
    playlist_profile_id: int | None = None
    optimization_profile: str | None = None


def export_m3u(
    session: Session,
    source_playlist_id: int,
    *,
    version_id: int | None = None,
    optimization_profile: OptimizationProfile | None = None,
    playlist_profile_id: int | None = None,
) -> ExportResult | None:
    """Render an original or custom playlist with optional stream optimization."""
    version = _get_version(session, source_playlist_id, version_id)
    if version is None:
        return None

    source_entries = session.scalars(
        select(PlaylistEntry)
        .options(selectinload(PlaylistEntry.channel), selectinload(PlaylistEntry.stream))
        .where(PlaylistEntry.source_playlist_version_id == version.id)
        .order_by(PlaylistEntry.original_position, PlaylistEntry.id)
    ).all()
    source_by_channel = {}
    for entry in source_entries:
        source_by_channel.setdefault(entry.channel_id, entry)

    profile = None
    if playlist_profile_id is not None:
        profile = session.scalar(
            select(PlaylistProfile)
            .options(selectinload(PlaylistProfile.entries))
            .where(
                PlaylistProfile.id == playlist_profile_id,
                PlaylistProfile.source_playlist_id == source_playlist_id,
            )
        )
        if profile is None:
            return None

    selected_entries = _select_entries(source_entries, source_by_channel, profile)
    optimization = None
    if optimization_profile is not None and selected_entries:
        optimization = _build_optimization(
            session,
            [entry.channel_id for entry in selected_entries],
            source_by_channel,
            optimization_profile,
        )

    output: list[str] = [version.original_header or "#EXTM3U"]
    optimized_count = 0
    fallback_count = 0

    profile_entries = {entry.channel_id: entry for entry in profile.entries} if profile else {}
    for entry in selected_entries:
        profile_entry = profile_entries.get(entry.channel_id)
        stream_url = entry.stream.url
        explicit_stream_id = profile_entry.selected_stream_id if profile_entry else None
        if explicit_stream_id is not None:
            explicit_stream = session.get(Stream, explicit_stream_id)
            if explicit_stream is not None:
                stream_url = explicit_stream.url
        elif optimization is not None:
            channel_plan = optimization.get(entry.channel_id)
            primary_stream_id = channel_plan.primary_stream_id if channel_plan else None
            if primary_stream_id is not None:
                primary_stream = session.get(Stream, primary_stream_id)
                if primary_stream is not None:
                    stream_url = primary_stream.url

        if stream_url != entry.stream.url:
            optimized_count += 1
        else:
            fallback_count += 1

        output.extend(entry.original_directives or [])
        output.append(_render_extinf(entry))
        output.append(stream_url)

    return ExportResult(
        content="\n".join(output) + "\n",
        source_playlist_version_id=version.id,
        source_playlist_version_number=version.version_number,
        channel_count=len(selected_entries),
        optimized_count=optimized_count,
        fallback_count=fallback_count,
        playlist_profile_id=playlist_profile_id,
        optimization_profile=optimization_profile.value if optimization_profile else None,
    )


def export_optimized_m3u(
    session: Session,
    source_playlist_id: int,
    version_id: int | None = None,
) -> ExportResult | None:
    """Backward-compatible export using the Fast optimization profile."""
    return export_m3u(
        session,
        source_playlist_id,
        version_id=version_id,
        optimization_profile=OptimizationProfile.FAST,
    )


def _select_entries(
    source_entries: list[PlaylistEntry],
    source_by_channel: dict[int, PlaylistEntry],
    profile: PlaylistProfile | None,
) -> list[PlaylistEntry]:
    if profile is None:
        return list(source_by_channel.values())
    return [
        source_by_channel[profile_entry.channel_id]
        for profile_entry in profile.entries
        if profile_entry.enabled and profile_entry.channel_id in source_by_channel
    ]


def _build_optimization(
    session: Session,
    channel_ids: list[int],
    source_by_channel: dict[int, PlaylistEntry],
    profile: OptimizationProfile,
):
    channels = session.scalars(
        select(Channel)
        .options(selectinload(Channel.streams))
        .where(Channel.id.in_(channel_ids))
        .order_by(Channel.canonical_name, Channel.id)
    ).all()
    stream_ids = {entry.stream_id for channel_id, entry in source_by_channel.items() if channel_id in channel_ids}
    tests = session.scalars(
        select(StreamTest)
        .where(StreamTest.stream_id.in_(stream_ids))
        .order_by(StreamTest.stream_id, StreamTest.completed_at, StreamTest.id)
    ).all() if stream_ids else []
    tests_by_stream: dict[int, list[StreamTest]] = {stream_id: [] for stream_id in stream_ids}
    for test in tests:
        tests_by_stream.setdefault(test.stream_id, []).append(test)

    stream_ids_by_channel = {
        channel.id: {stream.stream_id for stream in channel.streams}
        for channel in channels
    }
    plan = build_optimization_plan(channels, tests_by_stream, stream_ids_by_channel, profile)
    return {item.channel_id: item for item in plan.channels}


def _get_version(
    session: Session,
    source_playlist_id: int,
    version_id: int | None,
) -> SourcePlaylistVersion | None:
    statement = select(SourcePlaylistVersion).where(
        SourcePlaylistVersion.source_playlist_id == source_playlist_id,
        SourcePlaylistVersion.status == VersionStatus.COMPLETED.value,
    )
    if version_id is not None:
        statement = statement.where(SourcePlaylistVersion.id == version_id)
    else:
        statement = statement.order_by(SourcePlaylistVersion.version_number.desc()).limit(1)
    return session.scalar(statement)


def _render_extinf(entry: PlaylistEntry) -> str:
    if entry.raw_extinf:
        return entry.raw_extinf

    attributes = "".join(
        f' {key}="{value.replace(chr(34), chr(39))}"'
        for key, value in entry.original_attributes.items()
    )
    return f"#EXTINF:-1{attributes},{entry.original_name or ''}"
