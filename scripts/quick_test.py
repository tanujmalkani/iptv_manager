import argparse

from app.config import get_settings
from app.db.models import StreamTest
from app.db.session import SessionLocal
from app.testing import StreamTestEngine, StreamTestRunner


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Run sequential IPTV stream tests with startup and sustained playback."
    )
    parser.add_argument("--name", default="Stream Test", help="Test run name.")
    parser.add_argument(
        "--source-playlist-id",
        type=int,
        help="Only test streams associated with this source playlist.",
    )
    parser.add_argument(
        "--stream-id",
        type=int,
        action="append",
        dest="stream_ids",
        help="Test a specific stream ID; repeat the option for multiple streams.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=settings.quick_test_timeout_seconds,
        help=(
            "Startup timeout per stream in seconds "
            f"(default: {settings.quick_test_timeout_seconds})."
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Sustained playback duration per stream in seconds (default: 10).",
    )
    parser.add_argument(
        "--ffmpeg",
        default=settings.ffmpeg_binary,
        help=f"FFmpeg executable (default: {settings.ffmpeg_binary}).",
    )
    return parser


def _format_ms(value: float | None) -> str:
    return f"{value:.1f} ms" if value is not None else "-"


def _format_mbps(value: float | None) -> str:
    return f"{value / 1_000_000:.2f} Mbps" if value is not None else "-"


def _print_stream_result(stream_test: StreamTest, index: int, total: int) -> None:
    metrics = stream_test.extra_metrics or {}
    print(f"\n[{index}/{total}] Stream {stream_test.stream_id}")
    print(f"  Result:          {stream_test.result}")
    print(f"  Available:       {'yes' if stream_test.available else 'no'}")
    print(f"  DNS:              {_format_ms(stream_test.dns_ms)}")
    print(f"  Connect:          {_format_ms(stream_test.connect_ms)}")
    print(f"  TLS:              {_format_ms(stream_test.tls_ms)}")
    print(f"  HTTP response:    {_format_ms(stream_test.http_response_ms)}")
    print(f"  First data:       {_format_ms(stream_test.first_data_ms)}")
    print(f"  First frame:      {_format_ms(stream_test.first_frame_ms)}")
    print(f"  Duration:         {_format_ms(stream_test.test_duration_ms)}")
    print(f"  Playback:         {_format_ms(metrics.get('playback_duration_ms'))}")
    print(f"  Media bytes:      {stream_test.bytes_received or 0:,}")
    print(f"  Throughput:       {_format_mbps(metrics.get('throughput_bps'))}")
    print(f"  Decoded frames:   {metrics.get('decoded_frames', '-')}")
    print(f"  Resolution:       {metrics.get('resolution') or '-'}")
    fps = metrics.get("observed_fps")
    print(
        f"  Observed FPS:     {float(fps):.2f}"
        if fps is not None
        else "  Observed FPS:     -"
    )
    print(f"  Codec:            {metrics.get('codec') or '-'}")
    print(f"  Audio:            {'yes' if metrics.get('audio_present') else 'no'}")
    print(f"  Stable:           {'yes' if metrics.get('stable') else 'no'}")
    if stream_test.error_stage:
        print(f"  Error stage:      {stream_test.error_stage}")
    if stream_test.error_type:
        print(f"  Error type:       {stream_test.error_type}")


def main() -> int:
    args = build_parser().parse_args()
    runner = StreamTestRunner(
        StreamTestEngine(
            timeout_seconds=args.timeout,
            playback_duration_seconds=args.duration,
            ffmpeg_binary=args.ffmpeg,
        )
    )

    with SessionLocal() as session:
        print("Starting stream test...")
        test_run = runner.run(
            session,
            name=args.name,
            source_playlist_id=args.source_playlist_id,
            stream_ids=args.stream_ids,
            on_result=_print_stream_result,
        )

    print("\n" + "=" * 60)
    print(f"Stream test run: {test_run.id}")
    print(f"Status: {test_run.status}")
    print(f"Streams: {test_run.total_streams}")
    print(f"Completed: {test_run.completed_streams}")
    print(f"Successful: {test_run.successful_streams}")
    print(f"Failed: {test_run.failed_streams}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
