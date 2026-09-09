from __future__ import annotations

import re
from dataclasses import dataclass, field

_ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)=(?:"([^"]*)"|([^\s,]+))')


@dataclass(slots=True)
class M3UEntry:
    position: int
    name: str
    url: str
    duration: float | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    directives: list[str] = field(default_factory=list)
    raw_extinf: str | None = None


@dataclass(slots=True)
class M3UPlaylist:
    header: str
    entries: list[M3UEntry]
    directives: list[str] = field(default_factory=list)


def _parse_extinf(line: str) -> tuple[float | None, dict[str, str], str]:
    payload = line[len("#EXTINF:"):]
    duration_text, separator, title = payload.partition(",")
    try:
        duration = float(duration_text.strip()) if duration_text.strip() else None
    except ValueError:
        duration = None

    attributes: dict[str, str] = {}
    prefix = payload[: len(payload) - len(title)] if separator else payload
    for match in _ATTR_RE.finditer(prefix):
        value = match.group(2) if match.group(2) is not None else match.group(3) or ""
        attributes[match.group(1)] = value

    return duration, attributes, title.strip()


def parse_m3u(text: str) -> M3UPlaylist:
    """Parse tolerant Extended M3U text while preserving source directives."""
    raw_lines = text.splitlines()
    if not raw_lines:
        raise ValueError("Playlist is empty")

    lines = [
        line[1:] if index == 0 and line.startswith("\ufeff") else line
        for index, line in enumerate(raw_lines)
    ]
    first_content_index = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )
    if first_content_index is None:
        raise ValueError("Playlist is empty")

    first_line = lines[first_content_index].strip()
    has_header = first_line.upper().startswith("#EXTM3U")
    start_index = first_content_index + 1 if has_header else first_content_index
    header = lines[first_content_index] if has_header else "#EXTM3U"

    entries: list[M3UEntry] = []
    directives: list[str] = []
    pending_extinf: str | None = None
    pending_directives: list[str] = []

    for line in lines[start_index:]:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.upper().startswith("#EXTINF:"):
            pending_extinf = stripped
            continue

        if stripped.startswith("#"):
            pending_directives.append(stripped)
            continue

        if pending_extinf is None:
            entries.append(
                M3UEntry(
                    position=len(entries),
                    name="",
                    url=stripped,
                    directives=list(pending_directives),
                )
            )
            pending_directives.clear()
            continue

        duration, attributes, name = _parse_extinf(pending_extinf)
        entries.append(
            M3UEntry(
                position=len(entries),
                name=name,
                url=stripped,
                duration=duration,
                attributes=attributes,
                directives=list(pending_directives),
                raw_extinf=pending_extinf,
            )
        )
        pending_extinf = None
        pending_directives.clear()

    if pending_extinf is not None:
        pending_directives.insert(0, pending_extinf)
    directives.extend(pending_directives)

    return M3UPlaylist(header=header, entries=entries, directives=directives)
