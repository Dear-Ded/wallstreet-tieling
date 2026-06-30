#!/usr/bin/env python3
"""
multi_source_framework.py — Unified Multi-Source Adapter Framework.

Production-ready adapter base class with source registration, rate limiting,
exponential backoff, circuit breaker, response normalization, and audit trail.

Register adapters with @SourceRegistry.register("name") decorator.
Query all sources with SourceRegistry.query_all(entity_name="Foo Inc").
Each response returns a SourceResponse with evidence grade and normalized fields.
"""
from __future__ import annotations
import hashlib, json, threading, time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse

class EvidenceGrade(str, Enum):
    FACT = "fact"
    LEAD = "lead"
    WEAK_LEAD = "weak_lead"
    REJECTED = "rejected"

class SourceLane(str, Enum):
    MONEY = "money"; GOODS = "goods"; PEOPLE = "people"
    LEGAL = "legal"; REGISTRY = "registry"; RELATIONSHIP = "relationship"
    NEWS = "news"; CROSS = "cross"

class RateLimiter:
    def __init__(self, max_rps=5, backoff_base=1.5, max_backoff=60):
        self.max_rps = max_rps; self.min_interval = 1.0/max_rps if max_rps else 0
        self.backoff_base = backoff_base; self.max_backoff = max_backoff
        self._last = {}; self._lock = threading.Lock()
    def wait_if_needed(self, key):
        with self._lock:
            now = time.monotonic(); wait = self.min_interval - (now - self._last.get(key, 0))
            if wait > 0: time.sleep(wait)
            self._last[key] = time.monotonic()
    def backoff(self, attempt):
        return min(self.backoff_base ** attempt, self.max_backoff)

class CircuitBreaker:
    def __init__(self, threshold=5, recovery=120):
        self.threshold = threshold; self.recovery = recovery
        self._fails = defaultdict(int); self._open = {}; self._lock = threading.Lock()
    def is_open(self, key):
        with self._lock:
            if self._open.get(key, 0) > time.monotonic(): return True
            if key in self._open: self._fails[key] = 0; del self._open[key]
            return False
    def success(self, key):
        with self._lock: self._fails[key] = 0
    def failure(self, key):
        with self._lock:
            self._fails[key] += 1
            if self._fails[key] >= self.threshold: self._open[key] = time.monotonic() + self.recovery

@dataclass
class SourceResponse:
    source_name: str; source_type: str; evidence_grade: EvidenceGrade
    lane: SourceLane | str; fields: dict; raw_response: Any = None
    confidence: float = 0.5; evidence_id: str = ""; error: str = ""
    retry_count: int = 0; duration_ms: float = 0
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    def __post_init__(self):
        if not self.evidence_id:
            raw = json.dumps(self.fields, sort_keys=True, default=str)
            self.evidence_id = f"{self.source_name}:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
    def to_ledger(self):
        return {"evidence_id": self.evidence_id, "source_name": self.source_name,
            "source_type": self.source_type, "admission": self.evidence_grade.value,
            "confidence": self.confidence,
            "lane": self.lane.value if isinstance(self.lane, SourceLane) else str(self.lane),
            "fields": self.fields, "error": self.error or None,
            "retry_count": self.retry_count, "duration_ms": self.duration_ms, "timestamp": self.timestamp}

class SourceAdapter(ABC):
    source_name = "base"; source_type = "public_api"
    supported_lanes = []; rate_limit_rps = 5; max_retries = 3
    timeout_seconds = 30; requires_auth = False
    _limiter = None; _breaker = None; _audit = []
    def __init__(self, config=None): self.config = config or {}
    @classmethod
    def set_rate_limiter(cls, limiter): cls._limiter = limiter
    @classmethod
    def set_circuit_breaker(cls, breaker): cls._breaker = breaker
    def query(self, **params):
        key = f"{self.source_name}:{urlparse(self._build_url(**params)).netloc}"
        if self._breaker and self._breaker.is_open(key):
            return SourceResponse(source_name=self.source_name, source_type=self.source_type,
                evidence_grade=EvidenceGrade.REJECTED, lane=SourceLane.CROSS,
                fields={}, error=f"Circuit breaker open for {key}")
        last_err = ""
        for attempt in range(self.max_retries + 1):
            if self._limiter: self._limiter.wait_if_needed(key)
            start = time.monotonic()
            try:
                url = self._build_url(**params); raw = self._fetch(url)
                dur = (time.monotonic()-start)*1000; resp = self._normalize(raw, **params)
                resp.duration_ms = dur; resp.retry_count = attempt
                if self._breaker: self._breaker.success(key)
                return resp
            except Exception as e:
                dur = (time.monotonic()-start)*1000; last_err = f"{type(e).__name__}: {e}"
                if attempt < self.max_retries: time.sleep(RateLimiter().backoff(attempt))
                else:
                    if self._breaker: self._breaker.failure(key)
        return SourceResponse(source_name=self.source_name, source_type=self.source_type,
            evidence_grade=EvidenceGrade.REJECTED, lane=SourceLane.CROSS,
            fields={"params": params}, error=last_err, retry_count=self.max_retries)
    @abstractmethod
    def _build_url(self, **params) -> str: ...
    @abstractmethod
    def _fetch(self, url: str): ...
    @abstractmethod
    def _normalize(self, raw, **params) -> SourceResponse: ...

class SourceRegistry:
    _adapters = {}; _instances = {}; _lock = threading.Lock()
    @classmethod
    def register(cls, name=None):
        def dec(klass):
            key = name or klass.source_name
            with cls._lock: cls._adapters[key] = klass
            return klass
        return dec
    @classmethod
    def get(cls, name, config=None):
        with cls._lock:
            if name not in cls._instances:
                if name not in cls._adapters:
                    raise KeyError(f"No adapter '{name}'. Available: {list(cls._adapters)}")
                cls._instances[name] = cls._adapters[name](config)
            return cls._instances[name]
    @classmethod
    def list_all(cls):
        return {n: {"type": c.source_type, "auth": c.requires_auth,
            "lanes": [l.value for l in c.supported_lanes], "rps": c.rate_limit_rps}
            for n, c in cls._adapters.items()}
    @classmethod
    def query_all(cls, **params):
        return [cls.get(n).query(**params) for n in cls._adapters]
