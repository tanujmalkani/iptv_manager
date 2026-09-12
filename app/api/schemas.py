from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.optimization import OptimizationPlan, OptimizationProfile, OptimizationPolicy, POLICIES
from app.performance.stream_info import StreamTechnicalInfo


# Existing schema definitions remain unchanged above this point.
