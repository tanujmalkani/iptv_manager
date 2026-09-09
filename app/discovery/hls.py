from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urljoin

from app.discovery.models import VariantMetadata


@dataclass(slots=True)
class HLSVariant:
    url: str
    metadata: VariantMetadata


def _parse_attributes(value: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    current: list[str] = []
    quoted = False
    for char in value:
        if char == '"':
            quoted = not quoted
        if char == "," and not quoted:
            part = "".join(current)
            current.clear()
        else:
            current.append(char)
            continue
        if "=" in part:
            key, item = part.split("=", 1)
            attributes[key.strip().upper()] = item.strip().strip('"')
    part = "".join(current)
    if "=" in part:
        key, item = part.split("=", 1)
        attributes[key.strip().upper()] = item.strip().strip('"')
    return attributes


def _int_attribute(attributes: dict[str, str], key: str) -> int | None:
    try:
        return int(attributes[key]) if key in attributes else None
    except ValueError:
        return None


def _float_attribute(attributes: dict[str, str], key: str) -> float | None:
    try:
        return float(attributes[key]) if key in attributes else None
    except ValueError:
        return None


def parse_master_playlist(text: str, base_url: str) -> list[HLSVariant]:
    """Extract HLS variants from an #EXT-X-STREAM-INF master playlist."""
    lines = [line.strip() for line in text.splitlines()]
    variants: list[HLSVariant] = []

    for index, line in enumerate(lines):
        if not line.upper().startswith("#EXT-X-STREAM-INF:"):
            continue
        attributes = _parse_attributes(line.split(":", 1)[1])
        uri = next(
            (
                candidate
                for candidate in lines[index + 1 :]
                if candidate and not candidate.startswith("#")
            ),
            None,
        )
        if uri is None:
            continue

        resolution = attributes.get("RESOLUTION", "")
        width: int | None = None
        height: int | None = None
        if "x" in resolution.lower():
            width_text, height_text = resolution.lower().split("x", 1)
            with suppress(ValueError):
                width, height = int(width_text), int(height_text)

        metadata = VariantMetadata(
            bandwidth=_int_attribute(attributes, "BANDWIDTH"),
            average_bandwidth=_int_attribute(attributes, "AVERAGE-BANDWIDTH"),
            width=width,
            height=height,
            frame_rate=_float_attribute(attributes, "FRAME-RATE"),
            codecs=attributes.get("CODECS"),
        )
        variants.append(HLSVariant(url=urljoin(base_url, uri), metadata=metadata))

    return variants
