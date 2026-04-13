from __future__ import annotations

from enum import Enum


class BridgewoodReportingMode(str, Enum):
    AGGREGATED_ORDER = "aggregated_order"
    PER_FILL = "per_fill"
