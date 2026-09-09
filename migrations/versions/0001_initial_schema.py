"""Initial IPTV Manager schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_playlists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_location", sa.Text()),
        sa.Column("original_filename", sa.String(512)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_name", sa.String(512), nullable=False),
        sa.Column("normalized_name", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_merged", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_channels_normalized_name", "channels", ["normalized_name"])

    op.create_table(
        "streams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("protocol", sa.String(32)),
        sa.Column("hostname", sa.String(512)),
        sa.Column("port", sa.Integer()),
        sa.Column("path", sa.Text()),
        sa.Column("stream_kind", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("normalized_url", name="uq_stream_normalized_url"),
    )
    op.create_index("ix_streams_normalized_url", "streams", ["normalized_url"])
    op.create_index("ix_streams_hostname", "streams", ["hostname"])

    op.create_table(
        "source_playlist_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_playlist_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("raw_content_path", sa.Text()),
        sa.Column("original_header", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False, server_default="importing"),
        sa.ForeignKeyConstraint(["source_playlist_id"], ["source_playlists.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_playlist_id", "version_number", name="uq_playlist_version_number"),
        sa.UniqueConstraint("source_playlist_id", "content_hash", name="uq_playlist_content_hash"),
    )
    op.create_index("ix_source_playlist_versions_source_playlist_id", "source_playlist_versions", ["source_playlist_id"])

    op.create_table(
        "playlist_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_playlist_version_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("stream_id", sa.Integer(), nullable=False),
        sa.Column("original_position", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.Text()),
        sa.Column("original_group", sa.Text()),
        sa.Column("original_tvg_id", sa.Text()),
        sa.Column("original_tvg_name", sa.Text()),
        sa.Column("original_logo_url", sa.Text()),
        sa.Column("original_attributes", sa.JSON(), nullable=False),
        sa.Column("original_directives", sa.JSON(), nullable=False),
        sa.Column("raw_extinf", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_playlist_version_id"], ["source_playlist_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["stream_id"], ["streams.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_playlist_entries_source_playlist_version_id", "playlist_entries", ["source_playlist_version_id"])
    op.create_index("ix_playlist_entries_channel_id", "playlist_entries", ["channel_id"])
    op.create_index("ix_playlist_entries_stream_id", "playlist_entries", ["stream_id"])

    op.create_table(
        "channel_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("option_type", sa.String(32), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_playlist_id", sa.Integer()),
        sa.Column("playlist_entry_id", sa.Integer()),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_playlist_id"], ["source_playlists.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["playlist_entry_id"], ["playlist_entries.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("channel_id", "option_type", "value", name="uq_channel_option"),
    )
    op.create_index("ix_channel_options_channel_id", "channel_options", ["channel_id"])

    op.create_table(
        "channel_selections",
        sa.Column("channel_id", sa.Integer(), primary_key=True),
        sa.Column("name_option_id", sa.Integer()),
        sa.Column("logo_option_id", sa.Integer()),
        sa.Column("epg_id_option_id", sa.Integer()),
        sa.Column("epg_name_option_id", sa.Integer()),
        sa.Column("group_option_id", sa.Integer()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["name_option_id"], ["channel_options.id"]),
        sa.ForeignKeyConstraint(["logo_option_id"], ["channel_options.id"]),
        sa.ForeignKeyConstraint(["epg_id_option_id"], ["channel_options.id"]),
        sa.ForeignKeyConstraint(["epg_name_option_id"], ["channel_options.id"]),
        sa.ForeignKeyConstraint(["group_option_id"], ["channel_options.id"]),
    )

    op.create_table(
        "channel_merges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_channel_id", sa.Integer(), nullable=False),
        sa.Column("target_channel_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_channel_id", "target_channel_id", name="uq_channel_merge"),
        sa.CheckConstraint("source_channel_id != target_channel_id", name="ck_channel_merge_distinct"),
    )

    op.create_table(
        "channel_streams",
        sa.Column("channel_id", sa.Integer(), primary_key=True),
        sa.Column("stream_id", sa.Integer(), primary_key=True),
        sa.Column("first_seen", sa.DateTime(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stream_id"], ["streams.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "stream_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_stream_id", sa.Integer(), nullable=False),
        sa.Column("variant_stream_id", sa.Integer(), nullable=False),
        sa.Column("bandwidth", sa.Integer()),
        sa.Column("average_bandwidth", sa.Integer()),
        sa.Column("resolution_width", sa.Integer()),
        sa.Column("resolution_height", sa.Integer()),
        sa.Column("frame_rate", sa.Float()),
        sa.Column("codecs", sa.String(512)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["parent_stream_id"], ["streams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_stream_id"], ["streams.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("parent_stream_id", "variant_stream_id", name="uq_stream_variant"),
        sa.CheckConstraint("parent_stream_id != variant_stream_id", name="ck_stream_variant_distinct"),
    )
    op.create_index("ix_stream_variants_parent_stream_id", "stream_variants", ["parent_stream_id"])
    op.create_index("ix_stream_variants_variant_stream_id", "stream_variants", ["variant_stream_id"])

    op.create_table(
        "test_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_playlist_id", sa.Integer()),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("profile", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("total_streams", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_streams", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successful_streams", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_streams", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_playlist_id"], ["source_playlists.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_test_runs_source_playlist_id", "test_runs", ["source_playlist_id"])

    op.create_table(
        "stream_tests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("test_run_id", sa.Integer(), nullable=False),
        sa.Column("stream_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("test_type", sa.String(32), nullable=False),
        sa.Column("result", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("available", sa.Boolean()),
        sa.Column("error_stage", sa.String(64)),
        sa.Column("error_type", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("dns_ms", sa.Float()),
        sa.Column("connect_ms", sa.Float()),
        sa.Column("tls_ms", sa.Float()),
        sa.Column("http_response_ms", sa.Float()),
        sa.Column("manifest_ms", sa.Float()),
        sa.Column("first_data_ms", sa.Float()),
        sa.Column("first_frame_ms", sa.Float()),
        sa.Column("bytes_received", sa.Integer()),
        sa.Column("test_duration_ms", sa.Float()),
        sa.Column("throughput_bps", sa.Float()),
        sa.Column("extra_metrics", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["test_run_id"], ["test_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stream_id"], ["streams.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("test_run_id", "stream_id", "attempt_number", name="uq_stream_test_attempt"),
    )
    op.create_index("ix_stream_tests_test_run_id", "stream_tests", ["test_run_id"])
    op.create_index("ix_stream_tests_stream_id", "stream_tests", ["stream_id"])

    op.create_table(
        "playlist_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_playlist_id", sa.Integer()),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("selection_mode", sa.String(32), nullable=False, server_default="all"),
        sa.Column("stream_mode", sa.String(32), nullable=False, server_default="fastest_startup"),
        sa.Column("minimum_score", sa.Float()),
        sa.Column("minimum_width", sa.Integer()),
        sa.Column("maximum_startup_ms", sa.Float()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_playlist_id"], ["source_playlists.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_playlist_profiles_source_playlist_id", "playlist_profiles", ["source_playlist_id"])

    op.create_table(
        "playlist_profile_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["profile_id"], ["playlist_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_playlist_profile_groups_profile_id", "playlist_profile_groups", ["profile_id"])

    op.create_table(
        "playlist_profile_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("selected_stream_id", sa.Integer()),
        sa.Column("selected_name_option_id", sa.Integer()),
        sa.Column("selected_logo_option_id", sa.Integer()),
        sa.Column("selected_epg_id_option_id", sa.Integer()),
        sa.Column("selected_group_option_id", sa.Integer()),
        sa.ForeignKeyConstraint(["profile_id"], ["playlist_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["group_id"], ["playlist_profile_groups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selected_stream_id"], ["streams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selected_name_option_id"], ["channel_options.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selected_logo_option_id"], ["channel_options.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selected_epg_id_option_id"], ["channel_options.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["selected_group_option_id"], ["channel_options.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("profile_id", "position", name="uq_profile_position"),
    )
    op.create_index("ix_playlist_profile_entries_profile_id", "playlist_profile_entries", ["profile_id"])
    op.create_index("ix_playlist_profile_entries_channel_id", "playlist_profile_entries", ["channel_id"])


def downgrade() -> None:
    op.drop_table("playlist_profile_entries")
    op.drop_table("playlist_profile_groups")
    op.drop_table("playlist_profiles")
    op.drop_table("stream_tests")
    op.drop_table("test_runs")
    op.drop_table("stream_variants")
    op.drop_table("channel_streams")
    op.drop_table("channel_merges")
    op.drop_table("channel_selections")
    op.drop_table("channel_options")
    op.drop_table("playlist_entries")
    op.drop_table("source_playlist_versions")
    op.drop_table("streams")
    op.drop_table("channels")
    op.drop_table("source_playlists")
