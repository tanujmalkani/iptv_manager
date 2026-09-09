from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Channel, PlaylistEntry, SourcePlaylistVersion
from app.db.models.enums import VersionStatus
from app.performance.channels import get_channels_performance


@dataclass(frozen=True, slots=True)
class ExportResult:
    content: str
    source_playlist_version_id: int
    source_playlist_version_number: int
    channel_count: int
    optimized_count: int
    fallback_count: int


def export_optimized_m3u(
    session: Session,
    source_playlist_id: int,
    version_id: int | None = None,
) -> ExportResult | None:
    """Export one optimized entry per source channel using proven primary streams.

    Channels without a tested successful stream keep their original source URL so
    optimization never silently removes channel coverage.
    """
    version = _get_version(session, source_playlist_id, version_id)
    if version is None:
        return None

    entries = session.scalars(
        select(PlaylistEntry)
        .options(selectinload(PlaylistEntry.channel))
        .where(PlaylistEntry.source_playlist_version_id == version.id)
        .order_by(PlaylistEntry.original_position, PlaylistEntry.id)
    ).all()

    performances = {
        item.channel_id: item
        for item in get_channels_performance(session)
        if any(entry.channel_id == item.channel_id for entry in entries)
    }

    selected_entries: dict[int, PlaylistEntry] = {}
    for entry in entries:
        selected_entries.setdefault(entry.channel_id, entry)

    output: list[str] = [version.original_header or "#EXTM3U"]
    optimized_count = 0
    fallback_count = 0

    for entry in selected_entries.values():
        performance = performances.get(entry.channel_id)
        primary_stream_id = performance.primary_stream_id if performance else None
        stream_url = entry.stream.url
        if primary_stream_id is not None:
            ranked = next(
                item for item in performance.streams if item.stream_id == primary_stream_id
            )
            stream_url = _stream_url(session, primary_stream_id) or stream_url
            if stream_url != entry.stream.url:
                optimized_count += 1
            else:
                fallback_count += 1
        else:
            fallback_count += 1

        output.extend(entry.directives)
        output.append(_render_extinf(entry))
        output.append(stream_url)

    return ExportResult(
        content="\n".join(output) + "\n",
        source_playlist_version_id=version.id,
        source_playlist_version_number=version.version_number,
        channel_count=len(selected_entries),
        optimized_count=optimized_count,
        fallback_count=fallback_count,
    )


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


def _stream_url(session: Session, stream_id: int) -> str | None:
    stream = session.get(__import__("app.db.models", fromlist=["Stream"]).Stream, stream_id)
    return stream.url if stream else None


def _render_extinf(entry: PlaylistEntry) -> str:
    if entry.raw_extinf:
        return entry.raw_extinf

    duration = "-1" if entry.duration is None else _format_number(entry.duration)
    attributes = "".join(
        f' {key}="{value.replace(chr(34), chr(39))}"'
        for key, value in entry.original_attributes.items()
    )
    return f"#EXTINF:{duration}{attributes},{entry.original_name or ''}"


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)
