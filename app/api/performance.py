from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    ChannelPerformanceResponse,
    ChannelSummaryResponse,
    StreamPerformanceResponse,
)
from app.db.models import Stream, StreamTest
from app.db.session import get_db
from app.performance.aggregation import aggregate_stream_tests
from app.performance.channels import get_channel_performance, get_channels_performance

router = APIRouter(prefix="/api", tags=["performance"])


@router.get("/channels", response_model=list[ChannelSummaryResponse])
def list_channels_performance(
    session: Session = Depends(get_db),
) -> list[ChannelSummaryResponse]:
    """List channels with their current performance summary."""
    return [ChannelSummaryResponse.from_model(item) for item in get_channels_performance(session)]


@router.get("/channels/{channel_id}", response_model=ChannelPerformanceResponse)
def get_channel_performance_endpoint(
    channel_id: int,
    session: Session = Depends(get_db),
) -> ChannelPerformanceResponse:
    """Return all playable streams for a channel, ranked by historical performance."""
    performance = get_channel_performance(session, channel_id)
    if performance is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ChannelPerformanceResponse.from_model(performance)


@router.get("/streams/{stream_id}/performance", response_model=StreamPerformanceResponse)
def get_stream_performance_endpoint(
    stream_id: int,
    session: Session = Depends(get_db),
) -> StreamPerformanceResponse:
    """Return aggregated historical performance for one stream."""
    stream = session.get(Stream, stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Stream not found")

    tests = session.scalars(
        select(StreamTest)
        .where(StreamTest.stream_id == stream_id)
        .order_by(StreamTest.completed_at, StreamTest.id)
    ).all()
    performance = aggregate_stream_tests(stream_id, tests)
    return StreamPerformanceResponse.from_model(performance)
