import time
import hashlib
import json
import threading


DEFAULT_TTL = 300
DEFAULT_MAX_SIZE = 1000

TTL_MAP = {
    "live": 0,
    "cotations": 300,
    "fundamental": 300,
    "historical": 3600,
    "fields": 3600,
}


class ResponseCache:
    def __init__(self, defaultTTL=DEFAULT_TTL, maxSize=DEFAULT_MAX_SIZE, ttlMap=None):
        self.store = {}
        self.times = {}
        self.accessOrder = []
        self.defaultTTL = defaultTTL
        self.maxSize = maxSize
        self.ttlMap = ttlMap or TTL_MAP
        self.lock = threading.Lock()

    def makeKey(self, endpoint, **params):
        raw = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def get(self, key):
        with self.lock:
            if key not in self.store:
                return None
            endpoint = key.split(":")[0]
            ttl = self.ttlMap.get(endpoint, self.defaultTTL)
            if ttl <= 0:
                return None
            if time.time() - self.times[key] > ttl:
                del self.store[key]
                del self.times[key]
                if key in self.accessOrder:
                    self.accessOrder.remove(key)
                return None
            if key in self.accessOrder:
                self.accessOrder.remove(key)
            self.accessOrder.append(key)
            return self.store[key]

    def set(self, key, result):
        with self.lock:
            if key in self.store:
                self.accessOrder.remove(key)
            elif len(self.store) >= self.maxSize:
                oldest = self.accessOrder.pop(0)
                del self.store[oldest]
                del self.times[oldest]
            self.store[key] = result
            self.times[key] = time.time()
            self.accessOrder.append(key)
