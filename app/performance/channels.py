from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Channel, ChannelStream, PlaylistEntry, SourcePlaylistVersion, StreamTest
from app.performance.aggregation import StreamPerformance, aggregate_stream_tests
from app.performance.ranking import rank_channel_streams


@dataclass(frozen=True, slots=True)
class ChannelStreamRanking:
    channel_id: int
    stream_id: int
    rank: int
    score: float
    performance: StreamPerformance
    is_primary: bool


@dataclass(frozen=True, slots=True)
class ChannelPerformance:
    channel_id: int
    channel_name: str
    streams: tuple[ChannelStreamRanking, ...]
    primary_stream_id: int | None


def rank_streams_for_channel(
    channel: Channel,
    tests_by_stream: dict[int, Sequence[StreamTest]],
    stream_ids: set[int] | None = None,
) -> list[ChannelStreamRanking]:
    """Rank playable streams currently attached to a channel."""
    channel_streams = channel.streams
    if stream_ids is not None:
        channel_streams = [stream for stream in channel_streams if stream.stream_id in stream_ids]

    performances = [
        aggregate_stream_tests(stream.stream_id, tests_by_stream.get(stream.stream_id, ()))
        for stream in channel_streams
    ]
    ranked = rank_channel_streams(performances)

    primary_stream_id = next(
        (
            item.performance.stream_id
            for item in ranked
            if item.performance.successful_tests > 0
        ),
        None,
    )

    return [
        ChannelStreamRanking(
            channel_id=channel.id,
            stream_id=item.performance.stream_id,
            rank=item.rank,
            score=item.score,
            performance=item.performance,
            is_primary=item.performance.stream_id == primary_stream_id,
        )
        for item in ranked
    ]


def get_channel_performance(session: Session, channel_id: int) -> ChannelPerformance | None:
    """Return ranked playable streams and the recommended primary stream for a channel."""
    channel = session.scalar(
        select(Channel).options(selectinload(Channel.streams)).where(Channel.id == channel_id)
    )
    if channel is None:
        return None
    return _build_channel_performance(session, channel)


def get_channels_performance(
    session: Session,
    source_playlist_id: int | None = None,
) -> list[ChannelPerformance]:
    """Return ranked stream performance, optionally scoped to a source playlist."""
    statement = (
        select(Channel)
        .options(selectinload(Channel.streams))
        .join(ChannelStream, ChannelStream.channel_id == Channel.id)
    )
    if source_playlist_id is not None:
        statement = (
            statement
            .join(PlaylistEntry, PlaylistEntry.channel_id == Channel.id)
            .join(
                SourcePlaylistVersion,
                SourcePlaylistVersion.id == PlaylistEntry.source_playlist_version_id,
            )
            .where(SourcePlaylistVersion.source_playlist_id == source_playlist_id)
        )

    channels = session.scalars(
        statement.distinct().order_by(Channel.canonical_name, Channel.id)
    ).all()

    if source_playlist_id is None:
        stream_ids_by_channel = None
    else:
        stream_ids_by_channel = _load_playlist_stream_ids(session, source_playlist_id)

    stream_ids = {
        stream_id
        for channel in channels
        for stream_id in _stream_ids_for_channel(channel, stream_ids_by_channel)
    }
    tests_by_stream = _load_tests(session, stream_ids)
    return [
        _build_channel_performance_from_tests(
            channel,
            tests_by_stream,
            _stream_ids_for_channel(channel, stream_ids_by_channel),
        )
        for channel in channels
    ]


def _build_channel_performance(session: Session, channel: Channel) -> ChannelPerformance:
    stream_ids = {stream.stream_id for stream in channel.streams}
    return _build_channel_performance_from_tests(channel, _load_tests(session, stream_ids))


def _build_channel_performance_from_tests(
    channel: Channel,
    tests_by_stream: dict[int, list[StreamTest]],
    stream_ids: set[int] | None = None,
) -> ChannelPerformance:
    rankings = rank_streams_for_channel(channel, tests_by_stream, stream_ids)
    primary_stream_id = next((item.stream_id for item in rankings if item.is_primary), None)
    return ChannelPerformance(
        channel_id=channel.id,
        channel_name=channel.canonical_name,
        streams=tuple(rankings),
        primary_stream_id=primary_stream_id,
    )


def _load_playlist_stream_ids(
    session: Session,
    source_playlist_id: int,
) -> dict[int, set[int]]:
    rows = session.execute(
        select(PlaylistEntry.channel_id, PlaylistEntry.stream_id)
        .join(
            SourcePlaylistVersion,
            SourcePlaylistVersion.id == PlaylistEntry.source_playlist_version_id,
        )
        .where(SourcePlaylistVersion.source_playlist_id == source_playlist_id)
        .distinct()
    ).all()

    stream_ids_by_channel: dict[int, set[int]] = {}
    for channel_id, stream_id in rows:
        stream_ids_by_channel.setdefault(channel_id, set()).add(stream_id)
    return stream_ids_by_channel


def _stream_ids_for_channel(
    channel: Channel,
    stream_ids_by_channel: dict[int, set[int]] | None,
) -> set[int]:
    if stream_ids_by_channel is None:
        return {stream.stream_id for stream in channel.streams}
    return stream_ids_by_channel.get(channel.id, set())


def _load_tests(session: Session, stream_ids: set[int]) -> dict[int, list[StreamTest]]:
    tests_by_stream: dict[int, list[StreamTest]] = {stream_id: [] for stream_id in stream_ids}
    if not stream_ids:
        return tests_by_stream
    tests = session.scalars(
        select(StreamTest)
        .where(StreamTest.stream_id.in_(stream_ids))
        .order_by(StreamTest.stream_id, StreamTest.completed_at, StreamTest.id)
    ).all()
    for test in tests:
        tests_by_stream.setdefault(test.stream_id, []).append(test)
    return tests_by_stream
