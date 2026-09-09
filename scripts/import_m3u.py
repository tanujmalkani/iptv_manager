import argparse
from pathlib import Path

from app.db.session import SessionLocal
from app.importer.input import load_playlist_file, load_playlist_url
from app.importer.service import PlaylistImporter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import an M3U playlist into IPTV Manager.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Path to an M3U/M3U8 playlist file.")
    source.add_argument("--url", help="HTTP(S) URL of an M3U playlist.")
    parser.add_argument("--name", help="Override the source playlist name.")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.file:
        playlist_input = load_playlist_file(args.file)
    else:
        playlist_input = load_playlist_url(args.url)

    if args.name:
        playlist_input.name = args.name

    with SessionLocal() as session:
        result = PlaylistImporter().import_text(
            session,
            playlist_input.name,
            playlist_input.text,
            source_location=playlist_input.source_location,
        )

    print(f"Imported {result.entries} entries.")
    print(f"Channels: {result.channels}; unique streams: {result.unique_streams}.")
    print(f"Discovered streams: {result.discovered_streams}.")
    if result.identical_version:
        print("Playlist content was already imported; no new version created.")
    for warning in result.warnings:
        print(f"Warning: {warning}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
