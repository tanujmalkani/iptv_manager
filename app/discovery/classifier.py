from __future__ import annotations

from pathlib import PurePosixPath

from app.db.models.enums import StreamKind

_HLS_CONTENT_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
}

_VIDEO_CONTENT_PREFIXES = ("video/",)
_MEDIA_EXTENSIONS = {
    ".ts",
    ".mp4",
    ".m4v",
    ".mkv",
    ".webm",
    ".flv",
    ".aac",
    ".mp3",
    ".ac3",
}


def _content_type(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(";", 1)[0].strip().lower()


def is_hls_content_type(value: str | None) -> bool:
    return _content_type(value) in _HLS_CONTENT_TYPES


def classify_response(url: str, content_type: str | None, body: bytes) -> StreamKind:
    """Classify an HTTP response, using content inspection before URL hints."""
    normalized_type = _content_type(content_type)
    text = body.decode("utf-8-sig", errors="replace")
    stripped = text.lstrip("\ufeff \t\r\n")

    if stripped.startswith("#EXTM3U"):
        if "#EXT-X-STREAM-INF" in stripped:
            return StreamKind.MASTER_PLAYLIST
        playlist_tags = (
            "#EXTINF",
            "#EXT-X-TARGETDURATION",
            "#EXT-X-MEDIA-SEQUENCE",
        )
        if any(tag in stripped for tag in playlist_tags):
            return StreamKind.MEDIA_PLAYLIST
        m3u_suffixes = (".m3u8", ".m3u")
        if is_hls_content_type(normalized_type) or url.lower().split("?", 1)[0].endswith(
            m3u_suffixes
        ):
            return StreamKind.MEDIA_PLAYLIST

    if is_hls_content_type(normalized_type):
        return StreamKind.MEDIA_PLAYLIST

    if normalized_type and any(
        normalized_type.startswith(prefix) for prefix in _VIDEO_CONTENT_PREFIXES
    ):
        return StreamKind.MEDIA_STREAM

    path = PurePosixPath(url.split("?", 1)[0].lower())
    if path.suffix in _MEDIA_EXTENSIONS:
        return StreamKind.MEDIA_STREAM

    return StreamKind.UNKNOWN
