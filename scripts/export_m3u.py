from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.exporter import export_optimized_m3u


def main() -> None:
    parser = argparse.ArgumentParser(description="Export an optimized IPTV M3U playlist.")
    parser.add_argument("source_playlist_id", type=int, help="Source playlist ID")
    parser.add_argument("-o", "--output", default=None, help="Output M3U file path")
    parser.add_argument("--version-id", type=int, default=None, help="Specific completed version ID")
    args = parser.parse_args()

    with SessionLocal() as session:
        result = export_optimized_m3u(
            session,
            args.source_playlist_id,
            version_id=args.version_id,
        )

    if result is None:
        raise SystemExit("No completed playlist version found.")

    output_path = args.output or f"iptv-manager-optimized-v{result.source_playlist_version_number}.m3u"
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(result.content)

    print(f"Exported: {output_path}")
    print(f"Version:  {result.source_playlist_version_number}")
    print(f"Channels: {result.channel_count}")
    print(f"Optimized: {result.optimized_count}")
    print(f"Fallback:  {result.fallback_count}")


if __name__ == "__main__":
    main()
