from __future__ import annotations

import re
import subprocess
import threading
import time

from app.db.models.enums import ErrorType, TestResult
from app.testing.quick import QuickTestEngine, QuickTestResult

_STREAM_INFO_RE = re.compile(r"Video:\s*([^,\s]+)")
_RESOLUTION_RE = re.compile(r"\bs:\s*(\d+)x(\d+)")
_PTS_RE = re.compile(r"\bpts_time:\s*([0-9.]+)")
_FRAME_RE = re.compile(r"\]\s+n:\s*(\d+)\s+pts:")


class StreamTestEngine(QuickTestEngine):
    """Run startup and sustained playback measurements in one FFmpeg session."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        playback_duration_seconds: float = 10.0,
        ffmpeg_binary: str = "ffmpeg",
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, ffmpeg_binary=ffmpeg_binary)
        if playback_duration_seconds <= 0:
            raise ValueError("playback_duration_seconds must be greater than zero")
        self.playback_duration_seconds = playback_duration_seconds

    def test(self, url: str) -> QuickTestResult:
        started = time.monotonic()
        result = QuickTestResult()

        from urllib.parse import urlsplit

        if urlsplit(url).scheme in {"http", "https"}:
            network = self._test_http(url, self.timeout_seconds)
            result.dns_ms = network.dns_ms
            result.connect_ms = network.connect_ms
            result.tls_ms = network.tls_ms
            result.http_response_ms = network.http_response_ms
            result.first_data_ms = network.first_data_ms
            result.bytes_received = network.bytes_received

        playback = self._test_playback(url)
        result.first_frame_ms = playback["first_frame_ms"]
        result.extra_metrics = {
            "playback_duration_seconds": self.playback_duration_seconds,
            "playback_duration_ms": playback["playback_duration_ms"],
            "decoded_frames": playback["decoded_frames"],
            "resolution": playback["resolution"],
            "observed_fps": playback["observed_fps"],
            "codec": playback["codec"],
            "audio_present": playback["audio_present"],
            "stable": playback["stable"],
        }

        if playback["first_frame_ms"] is not None and playback["stable"]:
            result.result = TestResult.SUCCESS
            result.available = True
        else:
            result.error_stage = "playback"
            result.error_type = playback["error_type"]
            result.error_message = playback["error_message"]
        result.test_duration_ms = (time.monotonic() - started) * 1000.0
        return result

    def _test_playback(self, url: str) -> dict[str, object]:
        started = time.monotonic()
        process: subprocess.Popen[str]
        try:
            process = subprocess.Popen(
                [
                    self.ffmpeg_binary,
                    "-hide_banner",
                    "-loglevel",
                    "info",
                    "-i",
                    url,
                    "-map",
                    "0:v:0",
                    "-vf",
                    "showinfo",
                    "-f",
                    "null",
                    "-",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            return self._playback_failure(
                ErrorType.PROBE_FAILURE,
                f"FFmpeg binary not found: {self.ffmpeg_binary}",
            )
        except OSError as exc:
            return self._playback_failure(ErrorType.PROBE_FAILURE, str(exc))

        assert process.stderr is not None
        first_frame_ms: float | None = None
        first_pts: float | None = None
        last_pts: float | None = None
        decoded_frames = 0
        resolution: str | None = None
        codec: str | None = None
        audio_present = False
        stderr_lines: list[str] = []
        playback_started: float | None = None
        timer: threading.Timer | None = None

        try:
            for line in process.stderr:
                if len(stderr_lines) < 30:
                    stderr_lines.append(line.strip())
                if codec is None:
                    match = _STREAM_INFO_RE.search(line)
                    if match:
                        codec = match.group(1)
                if "Audio:" in line:
                    audio_present = True
                if resolution is None:
                    match = _RESOLUTION_RE.search(line)
                    if match:
                        resolution = f"{match.group(1)}x{match.group(2)}"

                frame_match = _FRAME_RE.search(line)
                if frame_match:
                    decoded_frames += 1
                    pts_match = _PTS_RE.search(line)
                    if pts_match:
                        pts = float(pts_match.group(1))
                        if first_pts is None:
                            first_pts = pts
                        last_pts = pts
                    if first_frame_ms is None:
                        first_frame_ms = (time.monotonic() - started) * 1000.0
                        playback_started = time.monotonic()
                        timer = threading.Timer(
                            self.playback_duration_seconds,
                            process.kill,
                        )
                        timer.daemon = True
                        timer.start()
        finally:
            if timer is not None:
                timer.cancel()
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stderr.close()

        playback_duration_ms = 0.0
        if playback_started is not None:
            playback_duration_ms = (time.monotonic() - playback_started) * 1000.0
        stable = (
            first_frame_ms is not None
            and playback_duration_ms >= self.playback_duration_seconds * 1000.0 * 0.95
        )

        if first_pts is not None and last_pts is not None and last_pts > first_pts:
            observed_fps = (decoded_frames - 1) / (last_pts - first_pts)
        else:
            observed_fps = None

        if stable:
            return {
                "first_frame_ms": first_frame_ms,
                "playback_duration_ms": playback_duration_ms,
                "decoded_frames": decoded_frames,
                "resolution": resolution,
                "observed_fps": observed_fps,
                "codec": codec,
                "audio_present": audio_present,
                "stable": True,
                "error_type": ErrorType.UNKNOWN,
                "error_message": None,
            }

        stderr = " ".join(line for line in stderr_lines if line)
        lower_stderr = stderr.lower()
        if first_frame_ms is None:
            if "unknown decoder" in lower_stderr or (
                "decoder" in lower_stderr and "not found" in lower_stderr
            ):
                error_type = ErrorType.CODEC_ERROR
            elif process.returncode == 0:
                error_type = ErrorType.NO_VIDEO
            else:
                error_type = ErrorType.DECODER_ERROR
            message = stderr or "FFmpeg failed before sustained playback."
        else:
            error_type = ErrorType.MEDIA_TIMEOUT
            message = "Stream ended before the requested sustained playback duration."

        return {
            "first_frame_ms": first_frame_ms,
            "playback_duration_ms": playback_duration_ms,
            "decoded_frames": decoded_frames,
            "resolution": resolution,
            "observed_fps": observed_fps,
            "codec": codec,
            "audio_present": audio_present,
            "stable": False,
            "error_type": error_type,
            "error_message": message,
        }

    @staticmethod
    def _playback_failure(error_type: ErrorType, message: str) -> dict[str, object]:
        return {
            "first_frame_ms": None,
            "playback_duration_ms": 0.0,
            "decoded_frames": 0,
            "resolution": None,
            "observed_fps": None,
            "codec": None,
            "audio_present": False,
            "stable": False,
            "error_type": error_type,
            "error_message": message,
        }
