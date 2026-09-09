from enum import StrEnum


class SourceType(StrEnum):
    FILE = "file"
    URL = "url"
    TEXT = "text"


class VersionStatus(StrEnum):
    IMPORTING = "importing"
    COMPLETED = "completed"
    FAILED = "failed"


class StreamKind(StrEnum):
    UNKNOWN = "unknown"
    MASTER_PLAYLIST = "master_playlist"
    MEDIA_PLAYLIST = "media_playlist"
    MEDIA_STREAM = "media_stream"


class ChannelOptionType(StrEnum):
    NAME = "name"
    LOGO = "logo"
    EPG_ID = "epg_id"
    EPG_NAME = "epg_name"
    GROUP = "group"


class TestRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TestType(StrEnum):
    QUICK = "quick"
    THROUGHPUT = "throughput"


class TestResult(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ErrorType(StrEnum):
    DNS_FAILURE = "dns_failure"
    CONNECTION_TIMEOUT = "connection_timeout"
    CONNECTION_FAILURE = "connection_failure"
    TLS_FAILURE = "tls_failure"
    HTTP_ERROR = "http_error"
    HTTP_TIMEOUT = "http_timeout"
    INVALID_M3U = "invalid_m3u"
    INVALID_MANIFEST = "invalid_manifest"
    NO_MEDIA = "no_media"
    MEDIA_TIMEOUT = "media_timeout"
    NO_VIDEO = "no_video"
    DECODER_ERROR = "decoder_error"
    CODEC_ERROR = "codec_error"
    PROBE_FAILURE = "probe_failure"
    STARTUP_TIMEOUT = "startup_timeout"
    UNKNOWN = "unknown"


class StreamMode(StrEnum):
    ORIGINAL = "original"
    BEST_SCORE = "best_score"
    FASTEST_STARTUP = "fastest_startup"
    HIGHEST_QUALITY = "highest_quality"
    MANUAL = "manual"
