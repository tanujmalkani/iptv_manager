from __future__ import annotations

from dataclasses import dataclass, field
import re


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
    lines = [line.lstrip("\ufeff").strip() for line in text.splitlines()]
    if not lines or not lines[0].upper().startswith("#EXTM3U"):
        raise ValueError("Playlist does not start with #EXTM3U")

    entries: list[M3UEntry] = []
    directives: list[str] = []
    pending_extinf: tuple[int, str] | None = None
    pending_directives: list[str] = []

    for line_number, line in enumerate(lines[1:], start=2):
        if not line:
            continue

        if line.startswith("#EXTINF:"):
            pending_extinf = (line_number, line)
            continue

        if line.startswith("#"):
            pending_directives.append(line)
            continue

        if pending_extinf is None:
            entries.append(
                M3UEntry(
                    position=len(entries),
                    name="",
                    url=line,
                    directives=list(pending_directives),
                )
            )
            pending_directives.clear()
            continue

        _, raw_extinf = pending_extinf
        duration, attributes, name = _parse_extinf(raw_extinf)
        entries.append(
            M3UEntry(
                position=len(entries),
                name=name,
                url=line,
                duration=duration,
                attributes=attributes,
                directives=list(pending_directives),
                raw_extinf=raw_extinf,
            )
        )
        pending_extinf = None
        pending_directives.clear()

    if pending_directives:
        directives.extend(pending_directives)

    return M3UPlaylist(header=lines[0], entries=entries, directives=directives)
