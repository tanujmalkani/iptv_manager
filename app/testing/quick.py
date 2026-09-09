from __future__ import annotations

import re
import socket
import ssl
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ChannelStream,
    PlaylistEntry,
    SourcePlaylistVersion,
    Stream,
    StreamTest,
    TestRun,
)
from app.db.models.enums import ErrorType, TestResult, TestRunStatus, TestType

_MAX_REDIRECTS = 5
_MAX_HEADER_BYTES = 64 * 1024
_SHOWINFO_FRAME_RE = re.compile(r"\]\s+n:\s*\d+\s+pts:")


@dataclass(slots=True)
class QuickTestResult:
    result: TestResult = TestResult.FAILED
    available: bool = False
    error_stage: str | None = None
    error_type: ErrorType | None = None
    error_message: str | None = None
    dns_ms: float | None = None
    connect_ms: float | None = None
    tls_ms: float | None = None
    http_response_ms: float | None = None
    manifest_ms: float | None = None
    first_data_ms: float | None = None
    first_frame_ms: float | None = None
    bytes_received: int | None = None
    test_duration_ms: float | None = None
    extra_metrics: dict = field(default_factory=dict)


@dataclass(slots=True)
class _NetworkResult:
    dns_ms: float | None = None
    connect_ms: float | None = None
    tls_ms: float | None = None
    http_response_ms: float | None = None
    first_data_ms: float | None = None
    bytes_received: int = 0
    error_stage: str | None = None
    error_type: ErrorType | None = None
    error_message: str | None = None


@dataclass(slots=True)
class _PhaseResult:
    status_code: int | None
    headers: dict[str, str]
    bytes_received: int
    dns_ms: float | None = None
    connect_ms: float | None = None
    tls_ms: float | None = None
    http_response_ms: float | None = None
    first_data_ms: float | None = None


class QuickTestEngine:
    """Measure network startup timing and verify the first decoded video frame."""

    def __init__(self, *, timeout_seconds: float = 10.0, ffmpeg_binary: str = "ffmpeg") -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.timeout_seconds = timeout_seconds
        self.ffmpeg_binary = ffmpeg_binary

    def test(self, url: str) -> QuickTestResult:
        started = time.monotonic()
        deadline = started + self.timeout_seconds
        result = QuickTestResult()

        if urlsplit(url).scheme in {"http", "https"}:
            network = self._test_http(url, self._remaining(deadline))
            result.dns_ms = network.dns_ms
            result.connect_ms = network.connect_ms
            result.tls_ms = network.tls_ms
            result.http_response_ms = network.http_response_ms
            result.first_data_ms = network.first_data_ms
            result.bytes_received = network.bytes_received

        remaining = self._remaining(deadline)
        if remaining <= 0:
            result.error_stage = "startup"
            result.error_type = ErrorType.STARTUP_TIMEOUT
            result.error_message = "Quick test timeout expired before FFmpeg verification."
            result.test_duration_ms = _elapsed_ms(started)
            return result

        first_frame_ms, error = self._test_first_frame(url, remaining)
        result.first_frame_ms = first_frame_ms
        if first_frame_ms is not None:
            result.result = TestResult.SUCCESS
            result.available = True
        else:
            result.error_stage = "decoder"
            result.error_type = error[0]
            result.error_message = error[1]
        result.test_duration_ms = _elapsed_ms(started)
        return result

    def _test_http(self, url: str, timeout_seconds: float) -> _NetworkResult:
        result = _NetworkResult()
        started = time.monotonic()
        current_url = url

        for redirect_count in range(_MAX_REDIRECTS + 1):
            remaining = timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                return _network_error(
                    result,
                    "http",
                    ErrorType.HTTP_TIMEOUT,
                    "HTTP quick-test timeout expired.",
                )
            try:
                phase = self._http_request(current_url, remaining)
            except socket.gaierror as exc:
                return _network_error(result, "dns", ErrorType.DNS_FAILURE, str(exc))
            except TimeoutError as exc:
                return _network_error(result, "connection", ErrorType.CONNECTION_TIMEOUT, str(exc))
            except ssl.SSLError as exc:
                return _network_error(result, "tls", ErrorType.TLS_FAILURE, str(exc))
            except OSError as exc:
                return _network_error(result, "connection", ErrorType.CONNECTION_FAILURE, str(exc))

            result.dns_ms = _sum_ms(result.dns_ms, phase.dns_ms)
            result.connect_ms = _sum_ms(result.connect_ms, phase.connect_ms)
            result.tls_ms = _sum_ms(result.tls_ms, phase.tls_ms)
            result.http_response_ms = _sum_ms(result.http_response_ms, phase.http_response_ms)
            if result.first_data_ms is None and phase.first_data_ms is not None:
                result.first_data_ms = _elapsed_ms(started)
            result.bytes_received += phase.bytes_received

            if phase.status_code is not None and 300 <= phase.status_code < 400:
                location = phase.headers.get("location")
                if not location:
                    return _network_error(
                        result,
                        "http",
                        ErrorType.HTTP_ERROR,
                        f"HTTP {phase.status_code} redirect without Location header.",
                    )
                if redirect_count == _MAX_REDIRECTS:
                    return _network_error(
                        result,
                        "http",
                        ErrorType.HTTP_ERROR,
                        "Too many HTTP redirects.",
                    )
                current_url = urljoin(current_url, location)
                continue

            if phase.status_code is not None and phase.status_code >= 400:
                return _network_error(
                    result,
                    "http",
                    ErrorType.HTTP_ERROR,
                    f"HTTP {phase.status_code}.",
                )
            if phase.first_data_ms is None:
                return _network_error(
                    result,
                    "http",
                    ErrorType.NO_MEDIA,
                    "HTTP response contained no body data.",
                )
            return result

        return _network_error(result, "http", ErrorType.HTTP_ERROR, "HTTP request failed.")

    def _http_request(self, url: str, timeout_seconds: float) -> _PhaseResult:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise OSError(f"Unsupported HTTP URL: {url}")

        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        phase = _PhaseResult(status_code=None, headers={}, bytes_received=0)
        deadline = time.monotonic() + timeout_seconds

        dns_start = time.monotonic()
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        phase.dns_ms = _elapsed_ms(dns_start)
        if not addresses:
            raise socket.gaierror(f"No address found for {parsed.hostname}")

        family, socktype, proto, _, sockaddr = addresses[0]
        raw_socket = socket.socket(family, socktype, proto)
        raw_socket.settimeout(max(0.1, deadline - time.monotonic()))
        try:
            connect_start = time.monotonic()
            raw_socket.connect(sockaddr)
            phase.connect_ms = _elapsed_ms(connect_start)

            if parsed.scheme == "https":
                tls_start = time.monotonic()
                context = ssl.create_default_context()
                sock: socket.socket = context.wrap_socket(
                    raw_socket,
                    server_hostname=parsed.hostname,
                )
                phase.tls_ms = _elapsed_ms(tls_start)
            else:
                sock = raw_socket

            sock.settimeout(max(0.1, deadline - time.monotonic()))
            try:
                host_header = parsed.hostname
                if parsed.port is not None:
                    host_header = f"{host_header}:{parsed.port}"
                request = (
                    f"GET {path} HTTP/1.1\r\n"
                    f"Host: {host_header}\r\n"
                    "User-Agent: IPTV-Manager/0.1\r\n"
                    "Accept: */*\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
                request_start = time.monotonic()
                sock.sendall(request)
                header_data = bytearray()
                while b"\r\n\r\n" not in header_data:
                    remaining = _MAX_HEADER_BYTES - len(header_data)
                    if remaining <= 0:
                        raise OSError("HTTP response headers exceed size limit")
                    chunk = sock.recv(min(4096, remaining))
                    if not chunk:
                        break
                    header_data.extend(chunk)
                phase.http_response_ms = _elapsed_ms(request_start)

                header_end = header_data.find(b"\r\n\r\n")
                if header_end < 0:
                    return phase
                header_block = bytes(header_data[:header_end]).decode("iso-8859-1")
                lines = header_block.split("\r\n")
                status_parts = lines[0].split(" ", 2)
                if len(status_parts) >= 2:
                    try:
                        phase.status_code = int(status_parts[1])
                    except ValueError:
                        phase.status_code = None
                for line in lines[1:]:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        phase.headers[key.strip().lower()] = value.strip()

                body = header_data[header_end + 4 :]
                if body:
                    phase.bytes_received += len(body)
                    phase.first_data_ms = _elapsed_ms(request_start)
                    return phase

                chunk = sock.recv(4096)
                if chunk:
                    phase.bytes_received += len(chunk)
                    phase.first_data_ms = _elapsed_ms(request_start)
                return phase
            finally:
                sock.close()
        except Exception:
            raw_socket.close()
            raise

    def _test_first_frame(
        self,
        url: str,
        timeout_seconds: float,
    ) -> tuple[float | None, tuple[ErrorType, str]]:
        started = time.monotonic()
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
                    "-frames:v",
                    "1",
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
            return None, (
                ErrorType.PROBE_FAILURE,
                f"FFmpeg binary not found: {self.ffmpeg_binary}",
            )
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
            return None, (
                ErrorType.STARTUP_TIMEOUT,
                "FFmpeg did not decode a video frame before timeout.",
            )

        stderr = " ".join(line for line in lines if line)
        lower_stderr = stderr.lower()
        if process.returncode == 0:
            return None, (
                ErrorType.NO_VIDEO,
                "FFmpeg completed without decoding a video frame.",
            )
        if "unknown decoder" in lower_stderr or (
            "decoder" in lower_stderr and "not found" in lower_stderr
        ):
            return None, (ErrorType.CODEC_ERROR, stderr or "FFmpeg decoder unavailable.")
        return None, (
            ErrorType.DECODER_ERROR,
            stderr or "FFmpeg failed before decoding a video frame.",
        )

    @staticmethod
    def _remaining(deadline: float) -> float:
        return deadline - time.monotonic()


class QuickTestRunner:
    """Run sequential quick tests for distinct playable streams and persist results."""

    def __init__(self, engine: QuickTestEngine | None = None) -> None:
        self.engine = engine or QuickTestEngine()

    def run(
        self,
        session: Session,
        *,
        name: str = "Quick Test",
        source_playlist_id: int | None = None,
        stream_ids: list[int] | None = None,
    ) -> TestRun:
        streams = self._select_streams(session, source_playlist_id, stream_ids)
        test_run = TestRun(
            source_playlist_id=source_playlist_id,
            name=name,
            profile=TestType.QUICK.value,
            status=TestRunStatus.RUNNING.value,
            started_at=_utcnow(),
            total_streams=len(streams),
            configuration_json={
                "test_type": TestType.QUICK.value,
                "timeout_seconds": self.engine.timeout_seconds,
                "ffmpeg_binary": self.engine.ffmpeg_binary,
            },
        )
        session.add(test_run)
        session.flush()

        try:
            for stream in streams:
                result = self.engine.test(stream.url)
                session.add(
                    StreamTest(
                        test_run_id=test_run.id,
                        stream_id=stream.id,
                        attempt_number=self._next_attempt_number(
                            session, test_run.id, stream.id
                        ),
                        test_type=TestType.QUICK.value,
                        result=result.result.value,
                        started_at=_utcnow(),
                        completed_at=_utcnow(),
                        available=result.available,
                        error_stage=result.error_stage,
                        error_type=result.error_type.value if result.error_type else None,
                        error_message=result.error_message,
                        dns_ms=result.dns_ms,
                        connect_ms=result.connect_ms,
                        tls_ms=result.tls_ms,
                        http_response_ms=result.http_response_ms,
                        manifest_ms=result.manifest_ms,
                        first_data_ms=result.first_data_ms,
                        first_frame_ms=result.first_frame_ms,
                        bytes_received=result.bytes_received,
                        test_duration_ms=result.test_duration_ms,
                        extra_metrics=result.extra_metrics,
                    )
                )
                test_run.completed_streams += 1
                if result.available:
                    test_run.successful_streams += 1
                else:
                    test_run.failed_streams += 1
                session.commit()
                session.refresh(test_run)

            test_run.status = TestRunStatus.COMPLETED.value
            test_run.completed_at = _utcnow()
            session.commit()
            session.refresh(test_run)
            return test_run
        except Exception:
            test_run.status = TestRunStatus.FAILED.value
            test_run.completed_at = _utcnow()
            session.commit()
            raise

    @staticmethod
    def _select_streams(
        session: Session,
        source_playlist_id: int | None,
        stream_ids: list[int] | None,
    ) -> list[Stream]:
        statement = (
            select(Stream)
            .join(ChannelStream, ChannelStream.stream_id == Stream.id)
            .distinct()
            .order_by(Stream.id)
        )
        if stream_ids is not None:
            if not stream_ids:
                return []
            statement = statement.where(Stream.id.in_(stream_ids))
        if source_playlist_id is not None:
            statement = (
                statement.join(PlaylistEntry, PlaylistEntry.stream_id == Stream.id)
                .join(
                    SourcePlaylistVersion,
                    SourcePlaylistVersion.id == PlaylistEntry.source_playlist_version_id,
                )
                .where(SourcePlaylistVersion.source_playlist_id == source_playlist_id)
            )
        return session.scalars(statement).all()

    @staticmethod
    def _next_attempt_number(session: Session, test_run_id: int, stream_id: int) -> int:
        latest = session.scalar(
            select(func.max(StreamTest.attempt_number)).where(
                StreamTest.test_run_id == test_run_id,
                StreamTest.stream_id == stream_id,
            )
        )
        return (latest or 0) + 1


def _network_error(
    result: _NetworkResult,
    stage: str,
    error_type: ErrorType,
    message: str,
) -> _NetworkResult:
    result.error_stage = stage
    result.error_type = error_type
    result.error_message = message
    return result


def _sum_ms(first: float | None, second: float | None) -> float | None:
    if first is None:
        return second
    if second is None:
        return first
    return first + second


def _elapsed_ms(started: float) -> float:
    return (time.monotonic() - started) * 1000.0


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
