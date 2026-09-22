import os, json, time
from typing import Any, Optional
try:
    import redis
except Exception:
    redis = None

# Provide safe default TTL if config is absent
try:
    from ..config import CACHE_TTL_SECONDS as _CACHE_TTL
except Exception:
    _CACHE_TTL = 300

class Cache:
    def __init__(self):
        self._local = {}
        self._r = None
        url = os.getenv("REDIS_URL")
        if redis and url:
            try:
                self._r = redis.Redis.from_url(url, decode_responses=True)
                self._r.ping()
            except Exception:
                self._r = None

    def get(self, key: str) -> Optional[Any]:
        if self._r:
            v = self._r.get(key)
            return json.loads(v) if v else None
        v = self._local.get(key)
        if not v: return None
        if v["exp"] < time.time():
            self._local.pop(key, None)
            return None
        return v["v"]

    def set(self, key: str, value: Any, ttl: int = _CACHE_TTL):
        if self._r:
            self._r.setex(key, ttl, json.dumps(value))
        else:
            self._local[key] = {"v": value, "exp": time.time() + ttl}

cache = Cache()
