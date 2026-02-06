from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExecutionReport:
    action: str  # open | close | none
    success: bool
    reason: str
    order: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

