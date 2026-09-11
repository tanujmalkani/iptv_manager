from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Channel,
    PlaylistEntry,
    SourcePlaylist,
    SourcePlaylistVersion,
    Stream,
)
from app.db.session import get_db
from app.main import app


def make_client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session


def test_playlist_profile_can_save_order_and_selection() -> None:
    client, session = make_client()
    try:
        playlist = SourcePlaylist(name="Test", source_type="text", source_location="test")
        version = SourcePlaylistVersion(
            source_playlist=playlist,
            version_number=1,
            content_hash="a" * 64,
            entry_count=2,
            status="completed",
        )
        first = Channel(canonical_name="BBC", normalized_name="bbc")
        second = Channel(canonical_name="CNN", normalized_name="cnn")
        first_stream = Stream(
            url="https://example.test/bbc.m3u8",
            normalized_url="https://example.test/bbc.m3u8",
            stream_kind="media_playlist",
        )
        second_stream = Stream(
            url="https://example.test/cnn.m3u8",
            normalized_url="https://example.test/cnn.m3u8",
            stream_kind="media_playlist",
        )
        session.add_all([playlist, version, first, second, first_stream, second_stream])
        session.flush()
        session.add_all(
            [
                PlaylistEntry(
                    source_playlist_version_id=version.id,
                    channel_id=first.id,
                    stream_id=first_stream.id,
                    original_position=0,
                    original_name="BBC",
                    original_attributes={},
                    original_directives=[],
                ),
                PlaylistEntry(
                    source_playlist_version_id=version.id,
                    channel_id=second.id,
                    stream_id=second_stream.id,
                    original_position=1,
                    original_name="CNN",
                    original_attributes={},
                    original_directives=[],
                ),
            ]
        )
        session.commit()

        payload = {
            "name": "Living Room",
            "source_playlist_id": playlist.id,
            "entries": [
                {"channel_id": second.id, "position": 0, "enabled": True},
                {"channel_id": first.id, "position": 1, "enabled": False},
            ],
        }
        response = client.post("/api/playlist-profiles", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Living Room"
        actual_entries = [
            (item["channel_id"], item["position"], item["enabled"])
            for item in body["entries"]
        ]
        assert actual_entries == [
            (second.id, 0, True),
            (first.id, 1, False),
        ]

        profile_id = body["id"]
        response = client.put(
            f"/api/playlist-profiles/{profile_id}",
            json={
                **payload,
                "entries": [
                    {"channel_id": first.id, "position": 0, "enabled": True},
                    {"channel_id": second.id, "position": 1, "enabled": True},
                ],
            },
        )
        assert response.status_code == 200
        assert [item["channel_id"] for item in response.json()["entries"]] == [
            first.id,
            second.id,
        ]
    finally:
        app.dependency_overrides.clear()
        session.close()
