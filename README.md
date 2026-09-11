# IPTV Manager

IPTV Manager imports IPTV/M3U playlists, discovers playable stream endpoints, measures stream startup and playback performance, ranks alternative streams, builds optimization recommendations, lets you maintain custom playlist profiles, and exports an M3U playlist using the selected streams.

The project is intentionally **player-independent**. It does not attempt to implement or control channel switching inside a specific IPTV player. Instead, it provides the stream measurements and optimized playlist output that a player can consume.

## What it does

### 1. Import and version playlists

The importer accepts M3U playlist content and creates a normalized database representation.

It:

- parses M3U entries and preserves the original playlist metadata/directives
- creates immutable source-playlist versions using a content hash
- detects identical playlist imports
- normalizes channel names and stream URLs
- de-duplicates streams across entries and versions
- records source metadata such as group, TVG ID/name, and logo

The command-line importer is available at `scripts/import_m3u.py`.

### 2. Discover playable streams

Stream discovery starts from each source URL and can recursively inspect HLS master playlists to find playable child streams/variants.

Discovered stream data includes information such as:

- final/redirected URL
- stream kind
- parent/child relationships
- HLS bandwidth and average bandwidth
- resolution
- frame rate
- codec information

Discovery is bounded by response size, recursion depth, and maximum stream limits.

### 3. Measure stream performance

The project has two test modes.

**Quick tests** are designed for frequent checks. They measure network startup phases and verify that FFmpeg can decode the first video frame:

`DNS → connect → TLS → HTTP response → first data → first decoded frame`

**Deep tests** add sustained playback measurement in the same FFmpeg session. They capture first-frame latency, playback duration, decoded frames, observed FPS, resolution, codec/audio information, throughput, and a stability result.

Tests are persisted as historical observations, including success/failure and error classification.

### 4. Run test campaigns

Test campaigns can run multiple streams concurrently. The web UI supports:

- Quick or Deep campaigns
- configurable concurrency (1–32 workers)
- campaign progress
- cancellation
- historical test runs and attempts

The default campaign concurrency is 4 workers.

### 5. Analyze and rank streams

Historical observations are aggregated per stream into metrics including:

- total/successful/failed tests
- success rate
- median and average first-frame latency
- P95 first-frame latency
- playback duration
- average FPS
- median and average throughput
- stability rate
- last-tested timestamp

Streams can then be ranked using reliability, startup speed, P95 latency, stability, and evidence of testing.

### 6. Optimize playlists

The optimizer currently provides three policies:

| Profile | Reliability | Speed | P95 | Stability | Evidence | Minimum success rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **Fast** | 20% | 50% | 20% | 0% | 10% | 50% |
| **Reliable** | 60% | 15% | 0% | 15% | 10% | 80% |
| **All** | 40% | 30% | 10% | 10% | 10% | 0% |

The optimizer excludes non-playable HLS master playlists and only promotes streams that satisfy the selected policy.

The web UI shows the score components and lets you apply recommendations to a playlist profile. Manual stream selections are preserved when recommendations are applied.

### 7. Build playlist profiles

A playlist profile can define a custom output playlist based on a source playlist version. Profile entries support:

- channel inclusion/exclusion
- ordering
- custom groups
- an explicitly selected stream per channel
- automatic stream selection using an optimization profile

Profile validation ensures selected channels and streams belong to the relevant completed source playlist version and that explicitly selected streams are playable.

### 8. Preview and export M3U

Before exporting, the application can preview the exact selection decisions and report warnings, including:

- optimized channels
- manual selections
- automatic selections
- fallbacks
- untested streams
- streams without successful tests
- invalid manual selections
- duplicate source entries

The application can then export an original or optimized M3U playlist. Export uses the latest completed playlist version by default and can also target a specific version.

## Web application

Run the application with Uvicorn:

```bash
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/`.

The web application currently provides playlist selection, channel/performance views, test campaigns, optimization recommendations, playlist profile editing, export preview, and M3U export.

## Command-line tools

The `scripts/` directory contains utilities for common workflows:

```text
scripts/import_m3u.py   Import an M3U playlist
scripts/quick_test.py   Run quick stream tests
scripts/export_m3u.py   Export a playlist
scripts/inspect_db.py   Inspect the local database
```

Use `--help` on each script for its current options.

## Project structure

```text
app/
  api/             FastAPI endpoints and response schemas
  db/              SQLAlchemy models and database session handling
  discovery/       Stream and HLS discovery
  importer/        Playlist import and normalization
  m3u/             M3U parser
  performance/     Performance aggregation and stream ranking
  testing/         Quick/deep tests and concurrent campaigns
  exporter.py      Playlist export and export preview
  optimization.py  Optimization policies and selection logic
  profiles.py      Playlist profile management
  main.py          FastAPI application
frontend/          Browser UI
migrations/        Alembic database migrations
scripts/           Command-line utilities
tests/             Automated test suite
```

## Development and CI

The project uses Python 3.11, SQLAlchemy, Alembic, FastAPI, Pydantic, FFmpeg for playback verification/measurement, pytest, and Ruff.

The GitHub Actions CI workflow currently validates:

1. dependency installation
2. `alembic upgrade head`
3. the automated test suite
4. Ruff linting

The current main branch has a green CI baseline.

## Testing locally

Install the project with development dependencies:

```bash
pip install -e ".[dev]"
```

Run database migrations:

```bash
alembic upgrade head
```

Run tests:

```bash
pytest -q
```

Run linting:

```bash
ruff check .
```

FFmpeg must be available on the system for real stream playback tests.

## Typical workflow

For a new user, the intended workflow is:

```text
M3U playlist
    ↓
Import playlist
    ↓
Inspect discovered channels/streams
    ↓
Run Quick tests regularly
    ↓
Run Deep tests periodically
    ↓
Review historical performance
    ↓
Choose Fast / Reliable / All optimization
    ↓
Apply recommendations and/or manual stream selections
    ↓
Preview export
    ↓
Export optimized M3U
    ↓
Use the resulting playlist in your IPTV player
```

The recommended manual re-test cadences shown in the UI are Quick Daily, Quick Every 3 Days, Deep Weekly, and Deep Monthly. These are currently recommendations for when to run tests; they are not an automated scheduler.

## Scope and design boundary

IPTV Manager optimizes the **stream endpoints and playlist that a player uses**. Actual channel-switch behavior is intentionally left to the IPTV player because buffering, demuxer/decoder behavior, connection reuse, prefetching, and other switching details vary by player.

For the purposes of this project, the important measurable inputs are stream startup/first-frame performance, sustained playback behavior, reliability, and throughput. The resulting rankings and optimized M3U are designed to give a player better stream choices without coupling IPTV Manager to a particular playback engine.
