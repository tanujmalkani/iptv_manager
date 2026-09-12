from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.db.models import Stream, StreamTest, StreamVariant


@dataclass(frozen=True, slots=True)
class StreamTechnicalInfo:
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


def build_stream_technical_info(
    stream: Stream,
    tests: Sequence[StreamTest] = (),
    variants: Sequence[StreamVariant] = (),
) -> StreamTechnicalInfo:
    """Combine advertised stream metadata with the latest playback observation."""
    sorted_tests = sorted(
        (test for test in tests if test.available),
        key=lambda test: (test.completed_at is None, test.completed_at, test.id),
        reverse=True,
    )
    latest = sorted_tests[0] if sorted_tests else None
    metrics = latest.extra_metrics if latest is not None else {}

    resolution = metrics.get("resolution")
    observed_fps = metrics.get("observed_fps")
    observed_codec = metrics.get("codec")
    audio_present = metrics.get("audio_present")

    ranked_variants = sorted(
        variants,
        key=lambda variant: (
            variant.bandwidth if variant.bandwidth is not None else -1,
            variant.average_bandwidth if variant.average_bandwidth is not None else -1,
        ),
        reverse=True,
    )
    variant = ranked_variants[0] if ranked_variants else None

    if (
        resolution is None
        and variant is not None
        and variant.resolution_width
        and variant.resolution_height
    ):
        resolution = f"{variant.resolution_width}x{variant.resolution_height}"
    return StreamTechnicalInfo(
        stream_id=stream.id,
        stream_kind=stream.stream_kind,
        protocol=stream.protocol,
        resolution=str(resolution) if resolution is not None else None,
        bitrate_bps=variant.bandwidth if variant is not None else None,
        average_bitrate_bps=variant.average_bandwidth if variant is not None else None,
        frame_rate=variant.frame_rate if variant is not None else None,
        codecs=variant.codecs if variant is not None else None,
        observed_fps=float(observed_fps) if observed_fps is not None else None,
        observed_codec=str(observed_codec) if observed_codec is not None else None,
        audio_present=bool(audio_present) if audio_present is not None else None,
    )
