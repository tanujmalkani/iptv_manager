from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import SourcePlaylist, SourcePlaylistVersion
from app.performance.aggregation import StreamPerformance
from app.performance.channels import ChannelPerformance, ChannelStreamRanking


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
    performance: StreamPerformanceResponse

    @classmethod
    def from_model(cls, ranking: ChannelStreamRanking) -> ChannelStreamResponse:
        return cls(
            stream_id=ranking.stream_id,
            rank=ranking.rank,
            score=ranking.score,
            is_primary=ranking.is_primary,
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
