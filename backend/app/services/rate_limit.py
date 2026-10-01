"""Login rate limiting — Redis-backed with an in-process fallback.

This is deliberately small: a fixed-window counter per (ip, email). It
establishes the architecture (swap in Redis for multi-instance deployments)
without adding a full throttling framework yet.
"""

from __future__ import annotations

import logging
import time

from app.core.config import Settings
from app.core.exceptions import RateLimitError

logger = logging.getLogger("securerag.ratelimit")


class LoginRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._redis = None
        self._redis_checked = False
        self._memory: dict[str, list[float]] = {}

    def _window_key(self, key: str) -> str:
        window = self.settings.rate_limit_login_window_seconds
        return f"ratelimit:login:{key}:{int(time.time() // window)}"

    async def _increment(self, key: str) -> int:
        window = self.settings.rate_limit_login_window_seconds
        redis = self._get_redis()
        if redis is not None:
            try:
                redis_key = self._window_key(key)
                count = await redis.incr(redis_key)
                if count == 1:
                    await redis.expire(redis_key, window + 1)
                return int(count)
            except Exception:  # noqa: BLE001 - fall back to memory on any redis error
                logger.warning("Redis unavailable for rate limiting; using memory fallback")
                self._redis = None
        now = time.monotonic()
        cutoff = now - window
        stamps = [stamp for stamp in self._memory.get(key, []) if stamp > cutoff]
        stamps.append(now)
        self._memory[key] = stamps
        # keep the fallback map small
        if len(self._memory) > 10_000:
            self._memory = {k: v for k, v in self._memory.items() if v and v[-1] > cutoff}
        return len(stamps)

    def _get_redis(self):  # pragma: no cover - exercised only with redis running
        if self.settings.redis_url and not self._redis_checked:
            self._redis_checked = True
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(self.settings.redis_url, decode_responses=True)
            except Exception:  # noqa: BLE001
                logger.warning("Could not create Redis client; using memory fallback")
                self._redis = None
        return self._redis

    async def check(self, key: str) -> None:
        """Raise 429 once the caller exceeds the configured attempts/window."""
        attempts = await self._increment(key)
        if attempts > self.settings.rate_limit_login_attempts:
            raise RateLimitError(
                "TOO_MANY_REQUESTS",
                f"Too many login attempts. Try again in "
                f"{self.settings.rate_limit_login_window_seconds} seconds.",
            )

    async def reset(self, key: str) -> None:
        """Clear the counter after a successful login."""
        self._memory.pop(key, None)
        redis = self._get_redis()
        if redis is not None:
            try:
                await redis.delete(self._window_key(key))
            except Exception:  # noqa: BLE001
                pass
