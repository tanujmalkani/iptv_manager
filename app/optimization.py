from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Channel, ChannelStream, PlaylistEntry, Stream, StreamTest, StreamVariant
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
    resolution_weight: float
    minimum_success_rate: float


POLICIES: dict[OptimizationProfile, OptimizationPolicy] = {
    OptimizationProfile.FAST: OptimizationPolicy(
        reliability_weight=0.20,
        speed_weight=0.40,
        p95_weight=0.20,
        stability_weight=0.00,
        evidence_weight=0.10,
        resolution_weight=0.10,
        minimum_success_rate=0.50,
    ),
    OptimizationProfile.RELIABLE: OptimizationPolicy(
        reliability_weight=0.60,
        speed_weight=0.10,
        p95_weight=0.00,
        stability_weight=0.15,
        evidence_weight=0.10,
        resolution_weight=0.05,
        minimum_success_rate=0.80,
    ),
    OptimizationProfile.ALL: OptimizationPolicy(
        reliability_weight=0.40,
        speed_weight=0.25,
        p95_weight=0.10,
        stability_weight=0.10,
        evidence_weight=0.10,
        resolution_weight=0.05,
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
    resolution_by_stream: dict[int, str | None] | None = None,
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
        if performance.success_rate < policy.minimum_success_rate and not (
            profile is OptimizationProfile.FAST and _has_successful_deep_validation(tests)
        ):
            continue
        performances.append(performance)

    ranked = rank_channel_streams_for_policy(
        performances,
        reliability_weight=policy.reliability_weight,
        speed_weight=policy.speed_weight,
        p95_weight=policy.p95_weight,
        stability_weight=policy.stability_weight,
        evidence_weight=policy.evidence_weight,
        resolution_weight=policy.resolution_weight,
        resolution_by_stream=resolution_by_stream,
    )
    primary = ranked[0].performance.stream_id if ranked else None
    return OptimizedChannel(
        channel_id=channel.id,
        channel_name=channel.canonical_name,
        candidates=tuple(ranked),
        primary_stream_id=primary,
    )


def _has_successful_deep_validation(tests: Sequence[StreamTest]) -> bool:
    """Treat a successful deep test as authoritative for Fast-profile eligibility."""
    return any(
        test.test_type == "deep" and test.available and test.result == "success" for test in tests
    )


def build_optimization_plan(
    channels: Sequence[Channel],
    tests_by_stream: dict[int, Sequence[StreamTest]],
    stream_ids_by_channel: dict[int, set[int]] | None = None,
    profile: OptimizationProfile = OptimizationProfile.FAST,
    resolution_by_stream: dict[int, str | None] | None = None,
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
                resolution_by_stream,
            )
            for channel in channels
        ),
    )


def load_playlist_stream_ids(
    session: Session,
    version_id: int,
) -> dict[int, set[int]]:
    """Return playable streams reachable from entries in one playlist version."""
    rows = session.execute(
        select(PlaylistEntry.channel_id, PlaylistEntry.stream_id)
        .where(PlaylistEntry.source_playlist_version_id == version_id)
        .distinct()
    ).all()

    roots_by_channel: dict[int, set[int]] = {}
    root_stream_ids: set[int] = set()
    for channel_id, stream_id in rows:
        if stream_id is None:
            continue
        roots_by_channel.setdefault(channel_id, set()).add(stream_id)
        root_stream_ids.add(stream_id)

    if not root_stream_ids:
        return {}

    variant_rows = session.execute(
        select(StreamVariant.parent_stream_id, StreamVariant.variant_stream_id)
    ).all()
    children_by_parent: dict[int, set[int]] = {}
    variant_stream_ids: set[int] = set()
    for parent_id, child_id in variant_rows:
        children_by_parent.setdefault(parent_id, set()).add(child_id)
        variant_stream_ids.add(child_id)

    stream_rows = session.execute(
        select(Stream.id, Stream.stream_kind).where(
            Stream.id.in_(root_stream_ids | variant_stream_ids)
        )
    ).all()
    kind_by_stream = {stream_id: kind for stream_id, kind in stream_rows}
    playable_kinds = {"media_playlist", "media_stream", "unknown"}

    stream_ids_by_channel: dict[int, set[int]] = {}
    for channel_id, roots in roots_by_channel.items():
        included: set[int] = set()
        pending = list(roots)
        seen: set[int] = set()
        while pending:
            stream_id = pending.pop()
            if stream_id in seen:
                continue
            seen.add(stream_id)
            if kind_by_stream.get(stream_id) in playable_kinds:
                included.add(stream_id)
            pending.extend(children_by_parent.get(stream_id, ()))
        stream_ids_by_channel[channel_id] = included
    return stream_ids_by_channel


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
