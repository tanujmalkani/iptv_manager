import argparse

from app.config import get_settings
from app.db.session import SessionLocal
from app.testing import QuickTestEngine, QuickTestRunner


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Run sequential IPTV quick tests against playable streams."
    )
    parser.add_argument("--name", default="Quick Test", help="Test run name.")
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
            "Overall timeout per stream in seconds "
            f"(default: {settings.quick_test_timeout_seconds})."
        ),
    )
    parser.add_argument(
        "--ffmpeg",
        default=settings.ffmpeg_binary,
        help=f"FFmpeg executable (default: {settings.ffmpeg_binary}).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    runner = QuickTestRunner(
        QuickTestEngine(timeout_seconds=args.timeout, ffmpeg_binary=args.ffmpeg)
    )

    with SessionLocal() as session:
        test_run = runner.run(
            session,
            name=args.name,
            source_playlist_id=args.source_playlist_id,
            stream_ids=args.stream_ids,
        )

    print(f"Quick test run: {test_run.id}")
    print(f"Status: {test_run.status}")
    print(f"Streams: {test_run.total_streams}")
    print(f"Completed: {test_run.completed_streams}")
    print(f"Successful: {test_run.successful_streams}")
    print(f"Failed: {test_run.failed_streams}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
