from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import PlaylistProfile, SourcePlaylist, SourcePlaylistVersion
from app.optimization import (
    POLICIES,
    OptimizationPlan,
    OptimizationProfile,
    OptimizedChannel,
)
from app.performance.aggregation import StreamPerformance
from app.performance.channels import ChannelPerformance, ChannelStreamRanking
from app.performance.stream_info import StreamTechnicalInfo


class StreamTechnicalInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stream_id: int
    stream_kind: str
    protocol: str | None
    resolution: str | None
    bitrate_bps: int | None
    average_bitrate_bps: int | None
    frame_rate: float | None
    codecs: str | None
    observed_fps: float | None
    observed_codec: str | None
    audio_present: bool | None

    @classmethod
    def from_model(cls, info: StreamTechnicalInfo) -> StreamTechnicalInfoResponse:
        return cls.model_validate(info)


class StreamPerformanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stream_id: int
    total_tests: int
    successful_tests: int
    failed_tests: int
    success_rate: float
    median_first_frame_ms: float | None
    average_first_frame_ms: float | None
    p95_first_frame_ms: float | None
    median_playback_duration_ms: float | None
    average_fps: float | None
    median_throughput_bps: float | None
    average_throughput_bps: float | None
    stable_tests: int
    stability_rate: float
    last_tested_at: datetime | None

    @classmethod
    def from_model(cls, performance: StreamPerformance) -> StreamPerformanceResponse:
        return cls.model_validate(performance)


class ChannelStreamResponse(BaseModel):
    stream_id: int
    rank: int
    score: float
    is_primary: bool
    stream_info: StreamTechnicalInfoResponse
    performance: StreamPerformanceResponse

    @classmethod
    def from_model(cls, ranking: ChannelStreamRanking) -> ChannelStreamResponse:
        return cls(
            stream_id=ranking.stream_id,
            rank=ranking.rank,
            score=ranking.score,
            is_primary=ranking.is_primary,
            stream_info=StreamTechnicalInfoResponse.from_model(ranking.stream_info),
            performance=StreamPerformanceResponse.from_model(ranking.performance),
        )


class ChannelPerformanceResponse(BaseModel):
    channel_id: int
    channel_name: str
    primary_stream_id: int | None
    streams: list[ChannelStreamResponse]

    @classmethod
    def from_model(cls, performance: ChannelPerformance) -> ChannelPerformanceResponse:
        return cls(
            channel_id=performance.channel_id,
            channel_name=performance.channel_name,
            primary_stream_id=performance.primary_stream_id,
            streams=[ChannelStreamResponse.from_model(item) for item in performance.streams],
        )


class ChannelSummaryResponse(BaseModel):
    channel_id: int
    channel_name: str
    primary_stream_id: int | None
    stream_count: int
    tested_stream_count: int
    best_first_frame_ms: float | None
    best_success_rate: float | None

    @classmethod
    def from_model(cls, performance: ChannelPerformance) -> ChannelSummaryResponse:
        tested = [item.performance for item in performance.streams if item.performance.total_tests]
        successful_latencies = [
            item.median_first_frame_ms
            for item in tested
            if item.median_first_frame_ms is not None
        ]
        success_rates = [item.success_rate for item in tested]
        return cls(
            channel_id=performance.channel_id,
            channel_name=performance.channel_name,
            primary_stream_id=performance.primary_stream_id,
            stream_count=len(performance.streams),
            tested_stream_count=len(tested),
            best_first_frame_ms=min(successful_latencies) if successful_latencies else None,
            best_success_rate=max(success_rates) if success_rates else None,
        )


class SourcePlaylistResponse(BaseModel):
    id: int
    name: str
    source_type: str
    source_location: str | None
    entry_count: int
    latest_version_id: int | None
    latest_version_number: int | None
    latest_version_entry_count: int | None

    @classmethod
    def from_model(
        cls,
        playlist: SourcePlaylist,
        version: SourcePlaylistVersion | None,
    ) -> SourcePlaylistResponse:
        return cls(
            id=playlist.id,
            name=playlist.name,
            source_type=playlist.source_type,
            source_location=playlist.source_location,
            entry_count=playlist.entry_count,
            latest_version_id=version.id if version else None,
            latest_version_number=version.version_number if version else None,
            latest_version_entry_count=version.entry_count if version else None,
        )


class PlaylistProfileEntryRequest(BaseModel):
    channel_id: int
    position: int = Field(ge=0)
    enabled: bool = True
    group_name: str | None = None
    selected_stream_id: int | None = Field(default=None, gt=0)


class PlaylistProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_playlist_id: int = Field(gt=0)
    description: str | None = None
    stream_mode: Literal["source", "fast", "reliable", "all"] = "source"
    entries: list[PlaylistProfileEntryRequest] = Field(default_factory=list)


class PlaylistProfileEntryResponse(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    position: int
    enabled: bool
    group_name: str | None
    selected_stream_id: int | None


class PlaylistProfileResponse(BaseModel):
    id: int
    source_playlist_id: int | None
    name: str
    description: str | None
    selection_mode: str
    stream_mode: str
    entries: list[PlaylistProfileEntryResponse]

    @classmethod
    def from_model(cls, profile: PlaylistProfile) -> PlaylistProfileResponse:
        return cls(
            id=profile.id,
            source_playlist_id=profile.source_playlist_id,
            name=profile.name,
            description=profile.description,
            selection_mode=profile.selection_mode,
            stream_mode=profile.stream_mode,
            entries=[
                PlaylistProfileEntryResponse(
                    id=entry.id,
                    channel_id=entry.channel_id,
                    channel_name=entry.channel.canonical_name,
                    position=entry.position,
                    enabled=entry.enabled,
                    group_name=entry.group.name if entry.group else None,
                    selected_stream_id=entry.selected_stream_id,
                )
                for entry in profile.entries
            ],
        )


class OptimizationCandidateResponse(BaseModel):
    stream_id: int
    rank: int
    score: float
    reliability_score: float
    speed_score: float
    p95_score: float
    stability_score: float
    evidence_score: float
    success_rate: float
    total_tests: int
    median_first_frame_ms: float | None
    p95_first_frame_ms: float | None
    stability_rate: float
    stream_info: StreamTechnicalInfoResponse

    @classmethod
    def from_model(
        cls,
        item,
        stream_info: StreamTechnicalInfo,
    ) -> OptimizationCandidateResponse:
        performance = item.performance
        return cls(
            stream_id=performance.stream_id,
            rank=item.rank,
            score=item.score,
            reliability_score=item.reliability_score,
            speed_score=item.speed_score,
            p95_score=item.p95_score,
            stability_score=item.stability_score,
            evidence_score=item.evidence_score,
            success_rate=performance.success_rate,
            total_tests=performance.total_tests,
            median_first_frame_ms=performance.median_first_frame_ms,
            p95_first_frame_ms=performance.p95_first_frame_ms,
            stability_rate=performance.stability_rate,
            stream_info=StreamTechnicalInfoResponse.from_model(stream_info),
        )


class OptimizationPolicyResponse(BaseModel):
    reliability_weight: float
    speed_weight: float
    p95_weight: float
    stability_weight: float
    evidence_weight: float
    minimum_success_rate: float


class OptimizationChannelResponse(BaseModel):
    channel_id: int
    channel_name: str
    primary_stream_id: int | None
    candidates: list[OptimizationCandidateResponse]

    @classmethod
    def from_model(
        cls,
        item: OptimizedChannel,
        stream_info_by_id: dict[int, StreamTechnicalInfo],
    ) -> OptimizationChannelResponse:
        candidates = [
            OptimizationCandidateResponse.from_model(
                candidate,
                stream_info_by_id[candidate.performance.stream_id],
            )
            for candidate in item.candidates
        ]
        return cls(
            channel_id=item.channel_id,
            channel_name=item.channel_name,
            primary_stream_id=item.primary_stream_id,
            candidates=candidates,
        )


class OptimizationPlanResponse(BaseModel):
    profile: OptimizationProfile
    version_number: int
    policy: OptimizationPolicyResponse
    channels: list[OptimizationChannelResponse]

    @classmethod
    def from_model(
        cls,
        plan: OptimizationPlan,
        version_number: int,
        stream_info_by_id: dict[int, StreamTechnicalInfo],
    ) -> OptimizationPlanResponse:
        policy = POLICIES[plan.profile]
        return cls(
            profile=plan.profile,
            version_number=version_number,
            policy=OptimizationPolicyResponse(
                reliability_weight=policy.reliability_weight,
                speed_weight=policy.speed_weight,
                p95_weight=policy.p95_weight,
                stability_weight=policy.stability_weight,
                evidence_weight=policy.evidence_weight,
                minimum_success_rate=policy.minimum_success_rate,
            ),
            channels=[
                OptimizationChannelResponse.from_model(item, stream_info_by_id)
                for item in plan.channels
            ],
        )


class ExportSelectionResponse(BaseModel):
    channel_id: int
    channel_name: str
    stream_info: StreamTechnicalInfoResponse
    performance: StreamPerformanceResponse
    optimized: bool
    fallback: bool


class ExportPreviewResponse(BaseModel):
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
    warnings: list[str]
    playlist_profile_id: int | None
    optimization_profile: str | None
    selections: list[ExportSelectionResponse]

    @classmethod
    def from_model(cls, preview) -> ExportPreviewResponse:
        return cls(
            source_playlist_version_id=preview.source_playlist_version_id,
            source_playlist_version_number=preview.source_playlist_version_number,
            source_entry_count=preview.source_entry_count,
            channel_count=preview.channel_count,
            duplicate_channel_entries=preview.duplicate_channel_entries,
            optimized_count=preview.optimized_count,
            manual_selection_count=preview.manual_selection_count,
            automatic_selection_count=preview.automatic_selection_count,
            fallback_count=preview.fallback_count,
            untested_count=preview.untested_count,
            no_successful_test_count=preview.no_successful_test_count,
            invalid_selection_count=preview.invalid_selection_count,
            warnings=list(preview.warnings),
            playlist_profile_id=preview.playlist_profile_id,
            optimization_profile=preview.optimization_profile,
            selections=[
                ExportSelectionResponse(
                    channel_id=selection.channel_id,
                    channel_name=selection.channel_name,
                    stream_info=StreamTechnicalInfoResponse.from_model(selection.stream_info),
                    performance=StreamPerformanceResponse.from_model(selection.performance),
                    optimized=selection.optimized,
                    fallback=selection.fallback,
                )
                for selection in preview.selections
            ],
        )
