from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def heartbeat_payload(*, cycle_id: str, status: str = "ok", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cycle_id": cycle_id,
        "status": status,
        "extra": extra or {},
    }

