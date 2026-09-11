from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Channel,
    PlaylistEntry,
    PlaylistProfile,
    SourcePlaylistVersion,
    Stream,
    StreamTest,
)
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


@dataclass(frozen=True, slots=True)
class ExportPreview:
    source_playlist_version_id: int
    source_playlist_version_number: int
    source_entry_count: int
    channel_count: int
    duplicate_channel_entries: int
    optimized_count: int
    manual_selection_count: int
    automatic_selection_count: int
    fallback_count: int
    untested_count: int
    no_successful_test_count: int
    invalid_selection_count: int
    warnings: tuple[str, ...]
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

    source_entries = _load_source_entries(session, version.id)
    source_by_channel = _source_by_channel(source_entries)
    profile = _load_profile(session, source_playlist_id, playlist_profile_id)
    if playlist_profile_id is not None and profile is None:
        return None

    selected_entries = _select_entries(source_by_channel, profile)
    optimization = None
    if optimization_profile is not None and selected_entries:
        optimization = _build_optimization(
            session,
            version.id,
            [entry.channel_id for entry in selected_entries],
            optimization_profile,
        )

    output: list[str] = [version.original_header or "#EXTM3U"]
    optimized_count = 0
    fallback_count = 0

    profile_entries = {entry.channel_id: entry for entry in profile.entries} if profile else {}
    for entry in selected_entries:
        profile_entry = profile_entries.get(entry.channel_id)
        chosen_stream_id, used_fallback, _ = _resolve_stream_choice(
            session,
            version.id,
            entry,
            profile_entry,
            optimization,
        )
        chosen_stream = session.get(Stream, chosen_stream_id)
        stream_url = chosen_stream.url if chosen_stream is not None else entry.stream.url

        if stream_url != entry.stream.url:
            optimized_count += 1
        if used_fallback:
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


def preview_m3u(
    session: Session,
    source_playlist_id: int,
    *,
    version_id: int | None = None,
    optimization_profile: OptimizationProfile | None = None,
    playlist_profile_id: int | None = None,
) -> ExportPreview | None:
    """Summarize the exact channel and stream decisions an M3U export will make."""
    version = _get_version(session, source_playlist_id, version_id)
    if version is None:
        return None

    source_entries = _load_source_entries(session, version.id)
    source_by_channel = _source_by_channel(source_entries)
    profile = _load_profile(session, source_playlist_id, playlist_profile_id)
    if playlist_profile_id is not None and profile is None:
        return None

    selected_entries = _select_entries(source_by_channel, profile)
    selected_channel_ids = {entry.channel_id for entry in selected_entries}
    playlist_stream_entries = (
        session.scalars(
            select(PlaylistEntry).where(
                PlaylistEntry.source_playlist_version_id == version.id,
                PlaylistEntry.channel_id.in_(selected_channel_ids),
            )
        ).all()
        if selected_channel_ids
        else []
    )
    all_candidate_stream_ids = {entry.stream_id for entry in playlist_stream_entries}

    optimization = None
    if optimization_profile is not None and selected_entries:
        optimization = _build_optimization(
            session,
            version.id,
            [entry.channel_id for entry in selected_entries],
            optimization_profile,
        )

    profile_entries = {entry.channel_id: entry for entry in profile.entries} if profile else {}
    test_stats = _stream_test_stats(session, all_candidate_stream_ids)
    optimized_count = 0
    manual_count = 0
    automatic_count = 0
    fallback_count = 0
    untested_count = 0
    no_successful_test_count = 0
    invalid_selection_count = 0
    warnings: list[str] = []

    for entry in selected_entries:
        profile_entry = profile_entries.get(entry.channel_id)
        chosen_stream_id, used_fallback, invalid_reason = _resolve_stream_choice(
            session,
            version.id,
            entry,
            profile_entry,
            optimization,
        )

        if profile_entry and profile_entry.selected_stream_id is not None:
            manual_count += 1
            if invalid_reason is not None:
                invalid_selection_count += 1
                warnings.append(
                    f"{entry.channel.canonical_name}: selected stream "
                    f"#{profile_entry.selected_stream_id} {invalid_reason}; source stream retained"
                )
        elif optimization is not None:
            automatic_count += 1
            if used_fallback:
                fallback_count += 1
                warnings.append(
                    f"{entry.channel.canonical_name}: no eligible tested stream for "
                    f"{optimization_profile.value} optimization; source stream retained"
                )
        else:
            fallback_count += 1

        if used_fallback and profile_entry and profile_entry.selected_stream_id is not None:
            fallback_count += 1

        if chosen_stream_id != entry.stream_id:
            optimized_count += 1

        stats = test_stats.get(chosen_stream_id, (0, 0))
        if stats[0] == 0:
            untested_count += 1
        if stats[1] == 0:
            no_successful_test_count += 1

    if untested_count:
        warnings.append(f"{untested_count} exported channel(s) use a stream with no test history")
    if no_successful_test_count:
        warnings.append(
            f"{no_successful_test_count} exported channel(s) use a stream with no successful test"
        )
    duplicate_count = len(source_entries) - len(source_by_channel)
    if duplicate_count:
        warnings.append(
            f"{duplicate_count} duplicate source entry(s) collapse to one exported channel entry"
        )

    return ExportPreview(
        source_playlist_version_id=version.id,
        source_playlist_version_number=version.version_number,
        source_entry_count=len(source_entries),
        channel_count=len(selected_entries),
        duplicate_channel_entries=duplicate_count,
        optimized_count=optimized_count,
        manual_selection_count=manual_count,
        automatic_selection_count=automatic_count,
        fallback_count=fallback_count,
        untested_count=untested_count,
        no_successful_test_count=no_successful_test_count,
        invalid_selection_count=invalid_selection_count,
        warnings=tuple(dict.fromkeys(warnings)),
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


def _resolve_stream_choice(
    session: Session,
    version_id: int,
    entry: PlaylistEntry,
    profile_entry,
    optimization,
) -> tuple[int, bool, str | None]:
    """Return the same validated stream choice used by preview and export."""
    chosen_stream_id = entry.stream_id
    explicit_stream_id = profile_entry.selected_stream_id if profile_entry else None
    if explicit_stream_id is not None:
        chosen_stream = session.get(Stream, explicit_stream_id)
        if chosen_stream is None:
            return chosen_stream_id, True, "is missing from the database"
        if chosen_stream.stream_kind == "master_playlist":
            return entry.stream_id, True, "is a master playlist"
        if not _stream_belongs_to_channel(
            session, version_id, entry.channel_id, explicit_stream_id
        ):
            return (
                chosen_stream_id,
                True,
                "is not a valid playable option for this playlist version",
            )
        return explicit_stream_id, False, None

    if optimization is not None:
        channel_plan = optimization.get(entry.channel_id)
        primary_stream_id = channel_plan.primary_stream_id if channel_plan else None
        if primary_stream_id is not None and session.get(Stream, primary_stream_id) is not None:
            return primary_stream_id, primary_stream_id == entry.stream_id, None
        return chosen_stream_id, True, None

    return chosen_stream_id, True, None


def _load_source_entries(session: Session, version_id: int) -> list[PlaylistEntry]:
    return session.scalars(
        select(PlaylistEntry)
        .options(selectinload(PlaylistEntry.channel), selectinload(PlaylistEntry.stream))
        .where(PlaylistEntry.source_playlist_version_id == version_id)
        .order_by(PlaylistEntry.original_position, PlaylistEntry.id)
    ).all()


def _source_by_channel(entries: list[PlaylistEntry]) -> dict[int, PlaylistEntry]:
    source_by_channel: dict[int, PlaylistEntry] = {}
    for entry in entries:
        source_by_channel.setdefault(entry.channel_id, entry)
    return source_by_channel


def _load_profile(
    session: Session,
    source_playlist_id: int,
    playlist_profile_id: int | None,
) -> PlaylistProfile | None:
    if playlist_profile_id is None:
        return None
    return session.scalar(
        select(PlaylistProfile)
        .options(selectinload(PlaylistProfile.entries))
        .where(
            PlaylistProfile.id == playlist_profile_id,
            PlaylistProfile.source_playlist_id == source_playlist_id,
        )
    )


def _select_entries(
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
    version_id: int,
    channel_ids: list[int],
    profile: OptimizationProfile,
):
    channels = session.scalars(
        select(Channel)
        .options(selectinload(Channel.streams))
        .where(Channel.id.in_(channel_ids))
        .order_by(Channel.canonical_name, Channel.id)
    ).all()
    playlist_entries = session.scalars(
        select(PlaylistEntry).where(
            PlaylistEntry.source_playlist_version_id == version_id,
            PlaylistEntry.channel_id.in_(channel_ids),
        )
    ).all()
    stream_ids = {entry.stream_id for entry in playlist_entries}
    tests = (
        session.scalars(
            select(StreamTest)
            .where(StreamTest.stream_id.in_(stream_ids))
            .order_by(StreamTest.stream_id, StreamTest.completed_at, StreamTest.id)
        ).all()
        if stream_ids
        else []
    )
    tests_by_stream: dict[int, list[StreamTest]] = {stream_id: [] for stream_id in stream_ids}
    for test in tests:
        tests_by_stream.setdefault(test.stream_id, []).append(test)

    stream_ids_by_channel: dict[int, set[int]] = {channel.id: set() for channel in channels}
    for entry in playlist_entries:
        stream_ids_by_channel.setdefault(entry.channel_id, set()).add(entry.stream_id)
    plan = build_optimization_plan(channels, tests_by_stream, stream_ids_by_channel, profile)
    return {item.channel_id: item for item in plan.channels}


def _stream_test_stats(session: Session, stream_ids: set[int]) -> dict[int, tuple[int, int]]:
    if not stream_ids:
        return {}
    tests = session.scalars(select(StreamTest).where(StreamTest.stream_id.in_(stream_ids))).all()
    stats: dict[int, tuple[int, int]] = {}
    for test in tests:
        total, successful = stats.get(test.stream_id, (0, 0))
        stats[test.stream_id] = (total + 1, successful + int(test.success))
    return stats


def _stream_belongs_to_channel(
    session: Session,
    version_id: int,
    channel_id: int,
    stream_id: int,
) -> bool:
    return session.scalar(
        select(PlaylistEntry.id)
        .join(Stream, Stream.id == PlaylistEntry.stream_id)
        .where(
            PlaylistEntry.source_playlist_version_id == version_id,
            PlaylistEntry.channel_id == channel_id,
            PlaylistEntry.stream_id == stream_id,
            Stream.stream_kind != "master_playlist",
        )
        .limit(1)
    ) is not None


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
