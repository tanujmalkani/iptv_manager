from __future__ import annotations

import threading
import time
from typing import Any

from app.db.models.enums import ErrorType
from app.testing.stream import StreamTestEngine


class _FakePipe:
    def __init__(self, lines: list[bytes] | None = None) -> None:
        self.lines = lines or []
        self.closed = False

    def __iter__(self):
        yield from self.lines

    def read(self, _size: int) -> bytes:
        return b""

    def close(self) -> None:
        self.closed = True


class _BlockingStderr(_FakePipe):
    def __init__(self) -> None:
        super().__init__()
        self.released = threading.Event()

    def __iter__(self):
        yield b"Input #0, hls, from 'test':\n"
        self.released.wait(timeout=1.0)


class _MediaStdout(_FakePipe):
    def __init__(self) -> None:
        super().__init__()
        self.first_read = True

    def read(self, _size: int) -> bytes:
        if self.first_read:
            self.first_read = False
            time.sleep(0.005)
            return b"x" * 1000
        return b""


class _PlaybackStderr(_FakePipe):
    def __init__(self, released: threading.Event) -> None:
        super().__init__()
        self.released = released

    def __iter__(self):
        yield b"Stream #0:0: Video: h264, yuv420p, 854x480 [SAR 1:1 DAR 427:240]\n"
        yield b"Stream #0:1: Audio: aac\n"
        yield b"[Parsed_showinfo_0] n:   0 pts:      0 pts_time:0.000\n"
        yield b"[Parsed_showinfo_0] n:   1 pts:   40000 pts_time:0.040\n"
        self.released.wait(timeout=1.0)


class _FakeProcess:
    def __init__(self, stderr: _FakePipe, stdout: _FakePipe) -> None:
        self.stderr = stderr
        self.stdout = stdout
        self.returncode: int | None = None
        self.killed = threading.Event()

    def poll(self) -> int | None:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9
        self.killed.set()
        if isinstance(self.stderr, (_BlockingStderr, _PlaybackStderr)):
            self.stderr.released.set()

    def wait(self) -> int:
        self.killed.wait(timeout=1.0)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


def _patch_popen(monkeypatch, process: _FakeProcess) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_popen(command: list[str], **_: Any) -> _FakeProcess:
        calls.append(command)
        return process

    monkeypatch.setattr("app.testing.stream.subprocess.Popen", fake_popen)
    return calls


def test_stream_test_measures_media_throughput_from_same_session(monkeypatch) -> None:
    released = threading.Event()
    stderr = _PlaybackStderr(released)
    stdout = _MediaStdout()
    process = _FakeProcess(stderr, stdout)
    calls = _patch_popen(monkeypatch, process)

    engine = StreamTestEngine(timeout_seconds=1, playback_duration_seconds=0.03)
    result = engine._test_playback("https://example.test/live.m3u8")

    assert result["stable"] is True
    assert result["media_bytes"] == 1000
    assert result["throughput_bps"] is not None
    assert result["throughput_bps"] > 0
    assert result["decoded_frames"] == 2
    assert result["resolution"] == "854x480"
    assert result["codec"] == "h264"
    assert result["audio_present"] is True
    assert "-c" in calls[0]
    assert calls[0][calls[0].index("-c") + 1] == "copy"
    assert "pipe:1" in calls[0]
    assert stdout.closed is True
    assert stderr.closed is True


def test_stream_test_enforces_startup_timeout(monkeypatch) -> None:
    stderr = _BlockingStderr()
    stdout = _FakePipe()
    process = _FakeProcess(stderr, stdout)
    _patch_popen(monkeypatch, process)

    engine = StreamTestEngine(timeout_seconds=0.02, playback_duration_seconds=0.1)
    started = time.monotonic()
    result = engine._test_playback("https://example.test/stalled.m3u8")
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert process.returncode == -9
    assert result["first_frame_ms"] is None
    assert result["stable"] is False
    assert result["throughput_bps"] is None
    assert result["error_type"] is ErrorType.MEDIA_TIMEOUT


def test_stream_test_rejects_non_positive_playback_duration() -> None:
    for duration in (0, -1):
        try:
            StreamTestEngine(playback_duration_seconds=duration)
        except ValueError as exc:
            assert str(exc) == "playback_duration_seconds must be greater than zero"
        else:
            raise AssertionError("expected ValueError")
