from __future__ import annotations

import re
import subprocess
import threading
import time
from collections.abc import Mapping

from app.db.models.enums import ErrorType
from app.discovery.url import http_headers_from_options, split_stream_reference
from app.testing.quick import (
    QuickTestEngine,
    QuickTestResult,
    _FFMPEG_PLAYBACK_OPTIONS,
    _SHOWINFO_FRAME_RE,
    _elapsed_ms,
)
from app.testing.stream import StreamTestEngine

_VIDEO_CODEC_RE = re.compile(r"Video:\s*([^,\s]+)")
_RESOLUTION_RE = re.compile(r"\bs:\s*(\d+)x(\d+)")
_PTS_RE = re.compile(r"\bpts_time:\s*([0-9.]+)")


def ffmpeg_headers_arg(headers: Mapping[str, str]) -> str:
    """Build FFmpeg's CRLF-delimited HTTP header argument."""
    return "".join(f"{key}: {value}\r\n" for key, value in headers.items())


class KodiAwareQuickTestEngine(QuickTestEngine):
    """Quick tester that understands Kodi-style request options appended to URLs."""

    def test(self, url: str) -> QuickTestResult:
        _, options = split_stream_reference(url)
        result = super().test(url)
        if options:
            result.extra_metrics["request_options"] = options
            result.extra_metrics["request_headers"] = http_headers_from_options(options)
        return result

    def _test_http(self, url: str, timeout_seconds: float):
        base_url, _ = split_stream_reference(url)
        return super()._test_http(base_url, timeout_seconds)

    def _test_first_frame(
        self,
        url: str,
        timeout_seconds: float,
    ) -> tuple[float | None, tuple[ErrorType, str]]:
        base_url, options = split_stream_reference(url)
        headers = http_headers_from_options(options)
        if not headers:
            return super()._test_first_frame(base_url, timeout_seconds)
        return self._test_first_frame_with_headers(base_url, timeout_seconds, headers)

    def _test_first_frame_with_headers(
        self,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str],
    ) -> tuple[float | None, tuple[ErrorType, str]]:
        started = time.monotonic()
        command = [
            self.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "info",
            *_FFMPEG_PLAYBACK_OPTIONS,
            "-headers",
            ffmpeg_headers_arg(headers),
            "-i",
            url,
            "-map",
            "0:v:0",
            "-vf",
            "showinfo",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            return None, (ErrorType.PROBE_FAILURE, f"FFmpeg binary not found: {self.ffmpeg_binary}")
        except OSError as exc:
            return None, (ErrorType.PROBE_FAILURE, str(exc))

        assert process.stderr is not None
        timer = threading.Timer(timeout_seconds, process.kill)
        timer.daemon = True
        timer.start()
        first_frame_ms: float | None = None
        lines: list[str] = []
        try:
            for line in process.stderr:
                if len(lines) < 20:
                    lines.append(line.strip())
                if _SHOWINFO_FRAME_RE.search(line):
                    first_frame_ms = _elapsed_ms(started)
                    process.terminate()
                    break
            process.wait(timeout=max(0.5, min(2.0, timeout_seconds)))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stderr.close()

        if first_frame_ms is not None:
            return first_frame_ms, (ErrorType.UNKNOWN, "")
        if time.monotonic() - started >= timeout_seconds:
            return None, (ErrorType.STARTUP_TIMEOUT, "FFmpeg did not decode a video frame before timeout.")

        stderr = " ".join(line for line in lines if line)
        lower_stderr = stderr.lower()
        if process.returncode == 0:
            return None, (ErrorType.NO_VIDEO, "FFmpeg completed without decoding a video frame.")
        if "unknown decoder" in lower_stderr or (
            "decoder" in lower_stderr and "not found" in lower_stderr
        ):
            return None, (ErrorType.CODEC_ERROR, stderr or "FFmpeg decoder unavailable.")
        return None, (ErrorType.DECODER_ERROR, stderr or "FFmpeg failed before decoding a video frame.")


class KodiAwareStreamTestEngine(StreamTestEngine):
    """Deep tester that passes Kodi-style HTTP headers to sustained FFmpeg playback."""

    def test(self, url: str) -> QuickTestResult:
        _, options = split_stream_reference(url)
        result = super().test(url)
        if options:
            result.extra_metrics["request_options"] = options
            result.extra_metrics["request_headers"] = http_headers_from_options(options)
        return result

    def _test_http(self, url: str, timeout_seconds: float):
        base_url, _ = split_stream_reference(url)
        return super()._test_http(base_url, timeout_seconds)

    def _test_playback(self, url: str) -> dict[str, object]:
        base_url, options = split_stream_reference(url)
        headers = http_headers_from_options(options)
        if not headers:
            return super()._test_playback(base_url)
        return self._test_playback_with_headers(base_url, headers)

    def _test_playback_with_headers(
        self,
        url: str,
        headers: Mapping[str, str],
    ) -> dict[str, object]:
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                [
                    self.ffmpeg_binary,
                    "-hide_banner",
                    "-loglevel",
                    "info",
                    *_FFMPEG_PLAYBACK_OPTIONS,
                    "-headers",
                    ffmpeg_headers_arg(headers),
                    "-i",
                    url,
                    "-map",
                    "0:v:0",
                    "-vf",
                    "showinfo",
                    "-f",
                    "null",
                    "-",
                    "-map",
                    "0:v:0",
                    "-c",
                    "copy",
                    "-f",
                    "mpegts",
                    "pipe:1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
        except FileNotFoundError:
            return self._playback_failure(
                ErrorType.PROBE_FAILURE,
                f"FFmpeg binary not found: {self.ffmpeg_binary}",
            )
        except OSError as exc:
            return self._playback_failure(ErrorType.PROBE_FAILURE, str(exc))

        assert process.stdout is not None
        assert process.stderr is not None
        media_bytes = 0
        media_bytes_after_first_frame = 0
        playback_started: float | None = None
        bytes_lock = threading.Lock()
        stderr_lines: list[str] = []
        stderr_lock = threading.Lock()
        first_frame_event = threading.Event()
        stderr_done = threading.Event()
        reader_done = threading.Event()
        first_pts: float | None = None
        last_pts: float | None = None
        decoded_frames = 0
        resolution: str | None = None
        codec: str | None = None
        audio_present = False

        def drain_media() -> None:
            nonlocal media_bytes, media_bytes_after_first_frame
            try:
                while True:
                    chunk = process.stdout.read(64 * 1024)
                    if not chunk:
                        break
                    with bytes_lock:
                        media_bytes += len(chunk)
                        if playback_started is not None:
                            media_bytes_after_first_frame += len(chunk)
            finally:
                reader_done.set()

        def read_stderr() -> None:
            nonlocal playback_started, first_pts, last_pts
            nonlocal decoded_frames, resolution, codec, audio_present
            try:
                for raw_line in process.stderr:
                    line = raw_line.decode("utf-8", errors="replace")
                    with stderr_lock:
                        if len(stderr_lines) < 30:
                            stderr_lines.append(line.strip())
                    if codec is None:
                        match = _VIDEO_CODEC_RE.search(line)
                        if match:
                            codec = match.group(1)
                    if "Audio:" in line:
                        audio_present = True
                    if resolution is None:
                        match = _RESOLUTION_RE.search(line)
                        if match:
                            resolution = f"{match.group(1)}x{match.group(2)}"
                    if _SHOWINFO_FRAME_RE.search(line):
                        decoded_frames += 1
                        pts_match = _PTS_RE.search(line)
                        if pts_match:
                            pts = float(pts_match.group(1))
                            if first_pts is None:
                                first_pts = pts
                            last_pts = pts
                        if not first_frame_event.is_set():
                            playback_started = time.monotonic()
                            first_frame_event.set()
            finally:
                stderr_done.set()

        reader = threading.Thread(target=drain_media, name="ffmpeg-media-reader", daemon=True)
        reader.start()
        stderr_reader = threading.Thread(
            target=read_stderr,
            name="ffmpeg-stderr-reader",
            daemon=True,
        )
        stderr_reader.start()

        first_frame_ms: float | None = None
        deadline = started + self.timeout_seconds
        while first_frame_event.wait(timeout=0.01) is False:
            if process.poll() is not None or stderr_done.is_set() or time.monotonic() >= deadline:
                break

        if first_frame_event.is_set() and playback_started is not None:
            first_frame_ms = (playback_started - started) * 1000.0
            playback_deadline = playback_started + self.playback_duration_seconds
            while time.monotonic() < playback_deadline:
                if process.poll() is not None:
                    break
                time.sleep(min(0.01, playback_deadline - time.monotonic()))

        if process.poll() is None:
            process.kill()
        process.wait()
        reader_done.wait(timeout=2.0)
        stderr_done.wait(timeout=2.0)
        reader.join(timeout=2.0)
        stderr_reader.join(timeout=2.0)
        process.stderr.close()
        process.stdout.close()

        playback_duration_ms = 0.0
        if playback_started is not None:
            playback_duration_ms = (time.monotonic() - playback_started) * 1000.0

        with bytes_lock:
            measured_bytes = media_bytes_after_first_frame
            total_media_bytes = media_bytes
        with stderr_lock:
            stderr = " ".join(line for line in stderr_lines if line)

        if first_frame_ms is None:
            lower_stderr = stderr.lower()
            if "allowed_segment_extensions" in lower_stderr or "extension_picky" in lower_stderr:
                error_type = ErrorType.INVALID_MANIFEST
            elif "unknown decoder" in lower_stderr or (
                "decoder" in lower_stderr and "not found" in lower_stderr
            ):
                error_type = ErrorType.CODEC_ERROR
            elif process.returncode == 0:
                error_type = ErrorType.NO_VIDEO
            elif (time.monotonic() - started) >= self.timeout_seconds * 0.95:
                error_type = ErrorType.MEDIA_TIMEOUT
            else:
                error_type = ErrorType.DECODER_ERROR
            return {
                "first_frame_ms": None,
                "playback_duration_ms": playback_duration_ms,
                "decoded_frames": decoded_frames,
                "resolution": resolution,
                "observed_fps": None,
                "codec": codec,
                "audio_present": audio_present,
                "stable": False,
                "media_bytes": total_media_bytes,
                "throughput_bps": None,
                "error_type": error_type,
                "error_message": stderr or "FFmpeg failed before sustained playback.",
            }

        stable = playback_duration_ms >= self.playback_duration_seconds * 1000.0 * 0.95
        observed_fps = (
            (decoded_frames - 1) / (last_pts - first_pts)
            if first_pts is not None and last_pts is not None and last_pts > first_pts
            else None
        )
        throughput_bps = (
            measured_bytes * 8 / (playback_duration_ms / 1000.0)
            if playback_duration_ms > 0 and measured_bytes > 0
            else None
        )
        return {
            "first_frame_ms": first_frame_ms,
            "playback_duration_ms": playback_duration_ms,
            "decoded_frames": decoded_frames,
            "resolution": resolution,
            "observed_fps": observed_fps,
            "codec": codec,
            "audio_present": audio_present,
            "stable": stable,
            "media_bytes": total_media_bytes,
            "throughput_bps": throughput_bps,
            "error_type": ErrorType.UNKNOWN if stable else ErrorType.MEDIA_TIMEOUT,
            "error_message": None if stable else "Stream ended before the requested sustained playback duration.",
        }


def install_kodi_request_support() -> None:
    """Make the application-facing testing classes Kodi-option aware."""
    import app.testing.deep as deep_module
    import app.testing.quick as quick_module
    import app.testing.stream as stream_module

    quick_module.QuickTestEngine = KodiAwareQuickTestEngine
    stream_module.StreamTestEngine = KodiAwareStreamTestEngine
    deep_module.DeepTestEngine = KodiAwareStreamTestEngine
