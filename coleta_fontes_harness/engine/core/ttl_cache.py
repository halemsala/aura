import time
import threading
class TTLCache:
    def __init__(self, default_ttl_seconds=300):
        self._store = {}
        self._ttl = default_ttl_seconds
        self._lock = threading.Lock()
    def set(self, key, value, ttl=None):
        with self._lock:
            self._store[key] = {"value": value, "expires": time.time() + (ttl or self._ttl)}
    def get(self, key, default=None):
        with self._lock:
            item = self._store.get(key)
            if not item: return default
            if time.time() > item["expires"]:
                del self._store[key]
                return default
            return item["value"]
    def clear_expired(self):
        now = time.time()
        with self._lock:
            expired_keys = [k for k, v in self._store.items() if now > v["expires"]]
            for k in expired_keys: del self._store[k]
            return len(expired_keys)
