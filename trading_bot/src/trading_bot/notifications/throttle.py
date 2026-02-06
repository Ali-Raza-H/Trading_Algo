from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Throttle:
    throttle_seconds: float
    _last: dict[str, float] = field(default_factory=dict)

    def allow(self, key: str) -> bool:
        now = time.time()
        last = self._last.get(key)
        if last is not None and (now - last) < float(self.throttle_seconds):
            return False
        self._last[key] = now
        return True

