from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from app.importer.service import ImportResult, PlaylistImporter


@dataclass(slots=True)
class PlaylistInput:
    name: str
    text: str
    source_location: str | None = None


def load_playlist_file(path: str | Path) -> PlaylistInput:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8-sig")
    return PlaylistInput(
        name=file_path.stem or file_path.name,
        text=text,
        source_location=str(file_path.resolve()),
    )


def load_playlist_url(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    client: httpx.Client | None = None,
) -> PlaylistInput:
    owns_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=True,
        timeout=timeout_seconds,
        headers={"User-Agent": "IPTV-Manager/0.1"},
    )
    try:
        response = http_client.get(url)
        response.raise_for_status()
        return PlaylistInput(
            name=_name_from_url(str(response.url)),
            text=response.content.decode("utf-8-sig"),
            source_location=url,
        )
    finally:
        if owns_client:
            http_client.close()


def import_input(
    importer: PlaylistImporter,
    session,
    playlist_input: PlaylistInput,
) -> ImportResult:
    return importer.import_text(
        session,
        playlist_input.name,
        playlist_input.text,
        source_location=playlist_input.source_location,
    )


def _name_from_url(url: str) -> str:
    path = url.rstrip("/").rsplit("/", 1)[-1]
    return path or "playlist"
