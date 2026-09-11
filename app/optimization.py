from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.db.models import Channel, ChannelStream, Stream, StreamTest
from app.performance.aggregation import StreamPerformance, aggregate_stream_tests
from app.performance.ranking import RankedStream, rank_channel_streams_for_policy


class OptimizationProfile(StrEnum):
    FAST = "fast"
    RELIABLE = "reliable"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class OptimizationPolicy:
    reliability_weight: float
    speed_weight: float
    p95_weight: float
    stability_weight: float
    evidence_weight: float
    minimum_success_rate: float


POLICIES: dict[OptimizationProfile, OptimizationPolicy] = {
    OptimizationProfile.FAST: OptimizationPolicy(
        reliability_weight=0.20,
        speed_weight=0.50,
        p95_weight=0.20,
        stability_weight=0.00,
        evidence_weight=0.10,
        minimum_success_rate=0.50,
    ),
    OptimizationProfile.RELIABLE: OptimizationPolicy(
        reliability_weight=0.60,
        speed_weight=0.15,
        p95_weight=0.00,
        stability_weight=0.15,
        evidence_weight=0.10,
        minimum_success_rate=0.80,
    ),
    OptimizationProfile.ALL: OptimizationPolicy(
        reliability_weight=0.40,
        speed_weight=0.30,
        p95_weight=0.10,
        stability_weight=0.10,
        evidence_weight=0.10,
        minimum_success_rate=0.00,
    ),
}


@dataclass(frozen=True, slots=True)
class OptimizedChannel:
    channel_id: int
    channel_name: str
    candidates: tuple[RankedStream, ...]
    primary_stream_id: int | None


@dataclass(frozen=True, slots=True)
class OptimizationPlan:
    profile: OptimizationProfile
    channels: tuple[OptimizedChannel, ...]


def build_channel_optimization(
    channel: Channel,
    tests_by_stream: dict[int, Sequence[StreamTest]],
    stream_ids: set[int] | None = None,
    profile: OptimizationProfile = OptimizationProfile.FAST,
) -> OptimizedChannel:
    performances: list[StreamPerformance] = []
    policy = POLICIES[profile]
    for channel_stream in channel.streams:
        if stream_ids is not None and channel_stream.stream_id not in stream_ids:
            continue
        tests = tests_by_stream.get(channel_stream.stream_id, ())
        performance = aggregate_stream_tests(channel_stream.stream_id, tests)
        if performance.successful_tests == 0:
            continue
        if performance.success_rate < policy.minimum_success_rate:
            continue
        performances.append(performance)

    ranked = rank_channel_streams_for_policy(
        performances,
        reliability_weight=policy.reliability_weight,
        speed_weight=policy.speed_weight,
        p95_weight=policy.p95_weight,
        stability_weight=policy.stability_weight,
        evidence_weight=policy.evidence_weight,
    )
    primary = ranked[0].performance.stream_id if ranked else None
    return OptimizedChannel(
        channel_id=channel.id,
        channel_name=channel.canonical_name,
        candidates=tuple(ranked),
        primary_stream_id=primary,
    )


def build_optimization_plan(
    channels: Sequence[Channel],
    tests_by_stream: dict[int, Sequence[StreamTest]],
    stream_ids_by_channel: dict[int, set[int]] | None = None,
    profile: OptimizationProfile = OptimizationProfile.FAST,
) -> OptimizationPlan:
    return OptimizationPlan(
        profile=profile,
        channels=tuple(
            build_channel_optimization(
                channel,
                tests_by_stream,
                None
                if stream_ids_by_channel is None
                else stream_ids_by_channel.get(channel.id, set()),
                profile,
            )
            for channel in channels
        ),
    )


def is_playable_stream(stream: Stream) -> bool:
    return stream.stream_kind != "master_playlist"


def eligible_stream_ids(
    channel_streams: Sequence[ChannelStream],
    streams: dict[int, Stream],
) -> set[int]:
    return {
        channel_stream.stream_id
        for channel_stream in channel_streams
        if channel_stream.stream_id in streams
        and is_playable_stream(streams[channel_stream.stream_id])
    }
