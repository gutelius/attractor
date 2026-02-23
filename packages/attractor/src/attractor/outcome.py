"""Outcome and StageStatus for pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageStatus(Enum):
    SUCCESS = "success"
    FAIL = "fail"
    PARTIAL_SUCCESS = "partial_success"
    RETRY = "retry"
    SKIPPED = "skipped"


@dataclass
class Outcome:
    status: StageStatus = StageStatus.SUCCESS
    preferred_label: str = ""
    suggested_next_ids: list[str] = field(default_factory=list)
    context_updates: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    failure_reason: str = ""

    @property
    def is_success(self) -> bool:
        return self.status in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS)

    @property
    def is_failure(self) -> bool:
        return self.status == StageStatus.FAIL

    @property
    def is_retry(self) -> bool:
        return self.status == StageStatus.RETRY
