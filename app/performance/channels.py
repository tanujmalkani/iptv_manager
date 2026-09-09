from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Channel, ChannelStream, StreamTest
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
) -> list[ChannelStreamRanking]:
    """Rank every playable stream currently attached to a channel."""
    performances = [
        aggregate_stream_tests(stream.stream_id, tests_by_stream.get(stream.stream_id, ()))
        for stream in channel.streams
    ]
    ranked = rank_channel_streams(performances)
    return [
        ChannelStreamRanking(
            channel_id=channel.id,
            stream_id=item.performance.stream_id,
            rank=item.rank,
            score=item.score,
            performance=item.performance,
            is_primary=item.rank == 1,
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


def get_channels_performance(session: Session) -> list[ChannelPerformance]:
    """Return ranked stream performance for every channel with playable streams."""
    channels = session.scalars(
        select(Channel)
        .options(selectinload(Channel.streams))
        .join(ChannelStream, ChannelStream.channel_id == Channel.id)
        .distinct()
        .order_by(Channel.canonical_name, Channel.id)
    ).all()

    stream_ids = {stream.stream_id for channel in channels for stream in channel.streams}
    tests_by_stream = _load_tests(session, stream_ids)
    return [_build_channel_performance_from_tests(channel, tests_by_stream) for channel in channels]


def _build_channel_performance(session: Session, channel: Channel) -> ChannelPerformance:
    stream_ids = {stream.stream_id for stream in channel.streams}
    return _build_channel_performance_from_tests(channel, _load_tests(session, stream_ids))


def _build_channel_performance_from_tests(
    channel: Channel,
    tests_by_stream: dict[int, list[StreamTest]],
) -> ChannelPerformance:
    rankings = rank_streams_for_channel(channel, tests_by_stream)
    return ChannelPerformance(
        channel_id=channel.id,
        channel_name=channel.canonical_name,
        streams=tuple(rankings),
        primary_stream_id=rankings[0].stream_id if rankings else None,
    )


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
