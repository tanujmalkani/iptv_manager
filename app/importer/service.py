from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Channel,
    ChannelOption,
    ChannelStream,
    PlaylistEntry,
    SourcePlaylist,
    SourcePlaylistVersion,
    Stream,
    StreamVariant,
)
from app.db.models.enums import ChannelOptionType, SourceType, StreamKind, VersionStatus
from app.discovery.models import DiscoveryResult, VariantMetadata
from app.discovery.service import StreamDiscovery
from app.discovery.url import normalize_url
from app.m3u.parser import M3UEntry, parse_m3u


ImportProgress = Callable[[str, int, int, str], None]


@dataclass(slots=True)
class ImportResult:
    source_playlist_id: int
    version_id: int
    version_number: int
    entries: int = 0
    channels: int = 0
    unique_streams: int = 0
    duplicate_urls: int = 0
    new_channels: int = 0
    discovered_streams: int = 0
    warnings: list[str] = field(default_factory=list)
    identical_version: bool = False


class PlaylistImporter:
    """Import an M3U playlist and persist recursively discovered streams."""

    def __init__(self, discovery: StreamDiscovery | None = None) -> None:
        self.discovery = discovery

    def import_text(
        self,
        session: Session,
        name: str,
        text: str,
        source_location: str | None = None,
        source_type: SourceType | None = None,
        progress: ImportProgress | None = None,
    ) -> ImportResult:
        self._report(progress, "parsing", 0, 0, "Parsing M3U content")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        playlist = parse_m3u(text)
        self._report(
            progress,
            "parsed",
            0,
            len(playlist.entries),
            f"Parsed {len(playlist.entries)} playlist entries",
        )
        source = self._get_or_create_source(
            session,
            name,
            source_location,
            source_type or (SourceType.URL if source_location else SourceType.TEXT),
        )

        existing = session.scalar(
            select(SourcePlaylistVersion).where(
                SourcePlaylistVersion.source_playlist_id == source.id,
                SourcePlaylistVersion.content_hash == content_hash,
            )
        )
        if existing is not None:
            self._report(
                progress,
                "complete",
                len(playlist.entries),
                len(playlist.entries),
                "Existing version detected",
            )
            return ImportResult(
                source_playlist_id=source.id,
                version_id=existing.id,
                version_number=existing.version_number,
                entries=existing.entry_count,
                identical_version=True,
            )

        latest = session.scalar(
            select(func.max(SourcePlaylistVersion.version_number)).where(
                SourcePlaylistVersion.source_playlist_id == source.id
            )
        )
        version = SourcePlaylistVersion(
            source_playlist=source,
            version_number=(latest or 0) + 1,
            content_hash=content_hash,
            entry_count=len(playlist.entries),
            original_header=playlist.header,
            status=VersionStatus.IMPORTING.value,
        )
        session.add(version)
        session.flush()

        result = ImportResult(
            source_playlist_id=source.id,
            version_id=version.id,
            version_number=version.version_number,
            entries=len(playlist.entries),
        )

        try:
            seen_entry_urls: set[str] = set()
            discovery_cache: dict[str, list[DiscoveryResult]] = {}
            total = len(playlist.entries)
            for index, entry in enumerate(playlist.entries, start=1):
                channel_name = entry.name or entry.attributes.get("tvg-name") or entry.url
                self._report(
                    progress,
                    "discovering",
                    index - 1,
                    total,
                    f"Discovering streams for {channel_name}",
                )
                normalized_entry_url = normalize_url(entry.url)
                if normalized_entry_url in seen_entry_urls:
                    result.duplicate_urls += 1
                seen_entry_urls.add(normalized_entry_url)
                self._import_entry(
                    session,
                    version,
                    source,
                    entry,
                    result,
                    discovery_cache,
                )
                self._report(
                    progress,
                    "discovering",
                    index,
                    total,
                    f"Processed {channel_name}",
                )

            self._report(progress, "saving", total, total, "Saving imported playlist version")
            version.status = VersionStatus.COMPLETED.value
            source.entry_count = len(playlist.entries)
            session.commit()
        except Exception:
            session.rollback()
            raise

        result.channels = self._count_channels(session, version.id)
        result.unique_streams = self._count_streams(session, version.id)
        self._report(
            progress,
            "complete",
            result.entries,
            result.entries,
            f"Import complete · {result.channels} channels · "
            f"{result.unique_streams} source streams",
        )
        return result

    @staticmethod
    def _report(
        progress: ImportProgress | None,
        stage: str,
        current: int,
        total: int,
        message: str,
    ) -> None:
        if progress is not None:
            progress(stage, current, total, message)

    def _get_or_create_source(
        self,
        session: Session,
        name: str,
        source_location: str | None,
        source_type: SourceType,
    ) -> SourcePlaylist:
        source = session.scalar(
            select(SourcePlaylist).where(
                SourcePlaylist.source_type == source_type.value,
                SourcePlaylist.source_location == source_location,
                SourcePlaylist.name == name,
            )
        )
        if source is None:
            source = SourcePlaylist(
                name=name,
                source_type=source_type.value,
                source_location=source_location,
            )
            session.add(source)
            session.flush()
        return source

    def _import_entry(
        self,
        session: Session,
        version: SourcePlaylistVersion,
        source: SourcePlaylist,
        entry: M3UEntry,
        result: ImportResult,
        discovery_cache: dict[str, list[DiscoveryResult]],
    ) -> None:
        channel_name = entry.name or entry.attributes.get("tvg-name") or entry.url
        normalized_name = normalize_channel_name(channel_name)
        channel = session.scalar(
            select(Channel).where(Channel.normalized_name == normalized_name)
        )
        if channel is None:
            channel = Channel(canonical_name=channel_name, normalized_name=normalized_name)
            session.add(channel)
            session.flush()
            result.new_channels += 1

        root_url = normalize_url(entry.url)
        root_results = self._discover(root_url, discovery_cache)
        stream_map: dict[str, Stream] = {}

        for discovered in root_results:
            stream_url = normalize_url(discovered.final_url or discovered.url)
            stream = self._get_or_create_stream(session, stream_url, discovered.kind)
            stream_map[stream_url] = stream
            if self._is_playable_kind(discovered.kind):
                self._add_channel_stream(session, channel, stream)
            result.discovered_streams += 1

        root_stream = stream_map.get(root_url)
        if root_stream is None and root_results:
            root_stream = stream_map.get(normalize_url(root_results[0].final_url))

        if root_stream is None:
            root_stream = self._get_or_create_stream(session, root_url, StreamKind.UNKNOWN)
            self._add_channel_stream(session, channel, root_stream)
            result.warnings.append(f"No discovery result for entry URL: {entry.url}")

        playlist_entry = PlaylistEntry(
            source_playlist_version=version,
            channel=channel,
            stream=root_stream,
            original_position=entry.position,
            original_name=entry.name or None,
            original_group=entry.attributes.get("group-title"),
            original_tvg_id=entry.attributes.get("tvg-id"),
            original_tvg_name=entry.attributes.get("tvg-name"),
            original_logo_url=entry.attributes.get("tvg-logo"),
            original_attributes=entry.attributes,
            original_directives=entry.directives,
            raw_extinf=entry.raw_extinf,
        )
        session.add(playlist_entry)
        session.flush()

        self._add_channel_options(session, channel, source, playlist_entry, entry)
        self._add_variants(session, root_results, stream_map)

    @staticmethod
    def _is_playable_kind(kind: StreamKind) -> bool:
        return kind in {
            StreamKind.MEDIA_PLAYLIST,
            StreamKind.MEDIA_STREAM,
            StreamKind.UNKNOWN,
        }

    def _discover(
        self,
        url: str,
        discovery_cache: dict[str, list[DiscoveryResult]],
    ) -> list[DiscoveryResult]:
        normalized_url = normalize_url(url)
        cached = discovery_cache.get(normalized_url)
        if cached is not None:
            return cached

        if self.discovery is not None:
            results = self.discovery.discover(normalized_url)
        else:
            with StreamDiscovery() as discovery:
                results = discovery.discover(normalized_url)

        for result in results:
            discovery_cache[normalize_url(result.url)] = results
            discovery_cache[normalize_url(result.final_url)] = results
        discovery_cache[normalized_url] = results
        return results

    def _get_or_create_stream(
        self,
        session: Session,
        url: str,
        kind: StreamKind,
    ) -> Stream:
        normalized = normalize_url(url)
        stream = session.scalar(select(Stream).where(Stream.normalized_url == normalized))
        if stream is not None:
            if stream.stream_kind == StreamKind.UNKNOWN.value and kind != StreamKind.UNKNOWN:
                stream.stream_kind = kind.value
            return stream

        parsed = urlsplit(normalized)
        stream = Stream(
            url=url,
            normalized_url=normalized,
            protocol=parsed.scheme or None,
            hostname=parsed.hostname,
            port=parsed.port,
            path=parsed.path or None,
            stream_kind=kind.value,
        )
        session.add(stream)
        session.flush()
        return stream

    def _add_channel_stream(
        self,
        session: Session,
        channel: Channel,
        stream: Stream,
    ) -> None:
        if session.get(ChannelStream, (channel.id, stream.id)) is None:
            session.add(ChannelStream(channel=channel, stream=stream))

    def _add_variants(
        self,
        session: Session,
        results: list[DiscoveryResult],
        stream_map: dict[str, Stream],
    ) -> None:
        for result_item in results:
            if result_item.parent_url is None or result_item.variant_metadata is None:
                continue

            parent = stream_map.get(normalize_url(result_item.parent_url))
            child = stream_map.get(normalize_url(result_item.final_url))
            if parent is None or child is None:
                continue

            metadata: VariantMetadata = result_item.variant_metadata
            exists = session.scalar(
                select(StreamVariant).where(
                    StreamVariant.parent_stream_id == parent.id,
                    StreamVariant.variant_stream_id == child.id,
                )
            )
            if exists is None:
                session.add(
                    StreamVariant(
                        parent_stream=parent,
                        variant_stream=child,
                        bandwidth=metadata.bandwidth,
                        average_bandwidth=metadata.average_bandwidth,
                        resolution_width=metadata.width,
                        resolution_height=metadata.height,
                        frame_rate=metadata.frame_rate,
                        codecs=metadata.codecs,
                    )
                )

    def _add_channel_options(
        self,
        session: Session,
        channel: Channel,
        source: SourcePlaylist,
        playlist_entry: PlaylistEntry,
        entry: M3UEntry,
    ) -> None:
        values = {
            ChannelOptionType.NAME.value: entry.name or entry.attributes.get("tvg-name"),
            ChannelOptionType.LOGO.value: entry.attributes.get("tvg-logo"),
            ChannelOptionType.EPG_ID.value: entry.attributes.get("tvg-id"),
            ChannelOptionType.EPG_NAME.value: entry.attributes.get("tvg-name"),
            ChannelOptionType.GROUP.value: entry.attributes.get("group-title"),
        }

        for option_type, value in values.items():
            if not value:
                continue

            exists = session.scalar(
                select(ChannelOption).where(
                    ChannelOption.channel_id == channel.id,
                    ChannelOption.option_type == option_type,
                    ChannelOption.value == value,
                )
            )
            if exists is None:
                session.add(
                    ChannelOption(
                        channel=channel,
                        option_type=option_type,
                        value=value,
                        source_playlist=source,
                        playlist_entry=playlist_entry,
                    )
                )

    @staticmethod
    def _count_channels(session: Session, version_id: int) -> int:
        return (
            session.scalar(
                select(func.count(func.distinct(PlaylistEntry.channel_id))).where(
                    PlaylistEntry.source_playlist_version_id == version_id
                )
            )
            or 0
        )

    @staticmethod
    def _count_streams(session: Session, version_id: int) -> int:
        return (
            session.scalar(
                select(func.count(func.distinct(PlaylistEntry.stream_id))).where(
                    PlaylistEntry.source_playlist_version_id == version_id
                )
            )
            or 0
        )


def normalize_channel_name(value: str) -> str:
    """Normalize names for exact matching without stripping quality markers."""
    return re.sub(r"\s+", " ", value).strip().casefold()
