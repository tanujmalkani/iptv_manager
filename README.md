# IPTV Manager

Local-first IPTV M3U playlist analyzer and optimizer.

## Development

```powershell
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
alembic upgrade head
pytest
uvicorn app.main:app --reload
```

## Import a playlist

```powershell
python scripts/import_m3u.py --file ".\path\to\playlist.m3u"
```

Or import directly from a URL:

```powershell
python scripts/import_m3u.py --url "https://example.invalid/playlist.m3u"
```

Inspect the local database:

```powershell
python scripts/inspect_db.py
```

## Quick stream test

Quick Test runs sequentially against distinct playable `ChannelStream` records. It records DNS, TCP connect, TLS, HTTP response, first-data, and FFmpeg first-decoded-video-frame timings. HTTP timing and FFmpeg verification use separate connections; the timings are not summed.

A stream is successful only when FFmpeg decodes a video frame. FFprobe is not used.

Run all playable streams:

```powershell
python scripts/quick_test.py
```

Test streams associated with one imported source playlist:

```powershell
python scripts/quick_test.py --source-playlist-id 1
```

Test selected stream IDs:

```powershell
python scripts/quick_test.py --stream-id 12 --stream-id 18
```

Override the timeout or FFmpeg executable:

```powershell
python scripts/quick_test.py --timeout 10 --ffmpeg ffmpeg
```

Test results are persisted in `test_runs` and `stream_tests` so individual attempts remain available for later analysis.
