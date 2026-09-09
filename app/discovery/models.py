from __future__ import annotations

from dataclasses import dataclass, field

from app.db.models.enums import StreamKind


@dataclass(slots=True)
class VariantMetadata:
    bandwidth: int | None = None
    average_bandwidth: int | None = None
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    codecs: str | None = None


@dataclass(slots=True)
class DiscoveryResult:
    url: str
    final_url: str
    kind: StreamKind
    content_type: str | None
    http_status: int | None
    parent_url: str | None
    depth: int
    variant_metadata: VariantMetadata | None = None
    error: str | None = None
    children: list[str] = field(default_factory=list)
