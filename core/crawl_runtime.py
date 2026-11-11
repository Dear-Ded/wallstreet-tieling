#!/usr/bin/env python3
"""Crawler runtime: request queue, sessions/cookies, proxy pool, throttle,
retries/backoff, checkpoints, Collector -> Mapper -> Consumer pipelines and
provenance-rich ``standardized_records``.

Patterns absorbed (re-implemented; no third-party code copied):

* XueQiuSuperSpider (MIT): Collector -> Mapper -> Consumer stages and a
  ``TimeWaitingStrategy`` (exponential wait with a ceiling). Its collectors
  swallow failures and return ``null``; here every failure is an explicit
  ``crawl_evidence_gap`` record instead.
* Scrapy (BSD-3): retry codes ``408/429/5xx/522/524`` with a bounded retry
  count, AutoThrottle-style per-domain delay derived from latency, robots.txt
  obedience, item pipelines.
* Crawlee (Apache-2.0): ``uniqueKey`` dedupe, request queue with
  handled/pending/failed state, ``SessionPool`` (cookie jar, usage/error
  score, retirement), proxy/session affinity, persisted state.
* Scrapling (BSD-3): JSON (not pickle) checkpoints and an adaptive fetch
  ladder (cheap static fetch first, escalate to a configured richer fetcher
  only when the page clearly needs it).

Challenge pages (CAPTCHA / WAF interstitials / 401/403 blocks) are never
"solved" here: the request is parked as ``human_verification_required`` and a
handoff gap record is emitted, so an operator or licensed provider can supply
an authorized session. Proxies are operator-configured (``WST_PROXY_URLS``);
nothing harvests public proxy lists.
"""
from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

RETRY_HTTP_CODES = frozenset({408, 429, 500, 502, 503, 504, 522, 524})
BLOCK_HTTP_CODES = frozenset({401, 403, 407, 412, 451})
CHALLENGE_MARKERS = (
    "captcha", "geetest", "hcaptcha", "recaptcha", "cf-chl", "challenge-platform",
    "验证码", "滑块", "安全验证", "访问验证", "acw_sc__v2", "_waf_", "请完成验证",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def unique_key_for(url: str, method: str = "GET", body: str = "") -> str:
    """Crawlee-style normalized key: lowercase scheme/host, sorted query, no fragment."""
    parts = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(parts.query, keep_blank_values=True)))
    path = parts.path or "/"
    normalized = urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))
    if method.upper() != "GET" or body:
        normalized = f"{method.upper()}:{normalized}:{hashlib.sha256(body.encode()).hexdigest()[:16]}"
    return normalized


# --------------------------------------------------------------------------
# Requests and queue
# --------------------------------------------------------------------------
@dataclass
class CrawlRequest:
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    label: str = ""
    depth: int = 0
    user_data: dict[str, Any] = field(default_factory=dict)
    unique_key: str = ""
    retry_count: int = 0
    max_retries: int | None = None
    not_before: float = 0.0
    session_id: str = ""
    errors: list[str] = field(default_factory=list)
    state: str = "pending"  # pending | in_progress | handled | failed | handoff

    def __post_init__(self) -> None:
        if not self.unique_key:
            self.unique_key = unique_key_for(self.url, self.method, self.body)

    @property
    def domain(self) -> str:
        return urllib.parse.urlsplit(self.url).netloc.lower()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrawlRequest":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class RequestQueue:
    """Deduplicating FIFO queue with handled/failed/handoff bookkeeping."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._requests: dict[str, CrawlRequest] = {}
        self._order: list[str] = []

    def add(self, request: CrawlRequest | str, **kwargs: Any) -> bool:
        req = request if isinstance(request, CrawlRequest) else CrawlRequest(url=request, **kwargs)
        with self._lock:
            if req.unique_key in self._requests:
                return False
            self._requests[req.unique_key] = req
            self._order.append(req.unique_key)
            return True

    def add_many(self, requests: Iterable[CrawlRequest | str]) -> int:
        return sum(1 for r in requests if self.add(r))

    def fetch_next(self) -> CrawlRequest | None:
        now = self._clock()
        with self._lock:
            for key in self._order:
                req = self._requests[key]
                if req.state == "pending" and req.not_before <= now:
                    req.state = "in_progress"
                    return req
        return None

    def next_ready_in(self) -> float | None:
        now = self._clock()
        with self._lock:
            waits = [max(0.0, r.not_before - now) for r in self._requests.values() if r.state == "pending"]
        return min(waits) if waits else None

    def mark_handled(self, req: CrawlRequest) -> None:
        with self._lock:
            req.state = "handled"

    def reclaim(self, req: CrawlRequest, *, delay: float, error: str) -> None:
        with self._lock:
            req.retry_count += 1
            req.errors.append(error)
            req.not_before = self._clock() + max(0.0, delay)
            req.state = "pending"

    def mark_failed(self, req: CrawlRequest, error: str, *, state: str = "failed") -> None:
        with self._lock:
            req.errors.append(error)
            req.state = state

    def is_finished(self) -> bool:
        with self._lock:
            return all(r.state in {"handled", "failed", "handoff"} for r in self._requests.values())

    def stats(self) -> dict[str, int]:
        with self._lock:
            out: dict[str, int] = {"total": len(self._requests)}
            for r in self._requests.values():
                out[r.state] = out.get(r.state, 0) + 1
            return out

    def requests(self, state: str | None = None) -> list[CrawlRequest]:
        with self._lock:
            return [self._requests[k] for k in self._order if state is None or self._requests[k].state == state]

    # ---- checkpoints (JSON, never pickle) ---------------------------------
    def to_checkpoint(self) -> dict[str, Any]:
        with self._lock:
            rows = []
            for key in self._order:
                row = self._requests[key].to_dict()
                if row["state"] == "in_progress":
                    row["state"] = "pending"  # resume re-runs interrupted requests
                row["not_before"] = 0.0
                rows.append(row)
        return {"type": "crawl_queue_checkpoint", "version": 1, "saved_at": utc_now(), "requests": rows}

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any], **kwargs: Any) -> "RequestQueue":
        if data.get("type") != "crawl_queue_checkpoint":
            raise ValueError("not a crawl_queue_checkpoint")
        queue = cls(**kwargs)
        for row in data.get("requests", []):
            req = CrawlRequest.from_dict(row)
            queue._requests[req.unique_key] = req
            queue._order.append(req.unique_key)
        return queue

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_checkpoint(), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, target)
        return target

    @classmethod
    def load(cls, path: str | Path, **kwargs: Any) -> "RequestQueue":
        return cls.from_checkpoint(json.loads(Path(path).read_text(encoding="utf-8")), **kwargs)


# --------------------------------------------------------------------------
# Proxies and sessions
# --------------------------------------------------------------------------
@dataclass
class ProxyEndpoint:
    url: str
    failures: int = 0
    successes: int = 0
    cooldown_until: float = 0.0

    @property
    def label(self) -> str:
        parts = urllib.parse.urlsplit(self.url)
        return f"{parts.scheme}://{parts.hostname}:{parts.port}" if parts.hostname else self.url


class ProxyPool:
    """Operator-configured proxies with round-robin, failure cooldown and stats."""

    def __init__(self, urls: Iterable[str] = (), *, max_failures: int = 3, cooldown_s: float = 300.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._proxies = [ProxyEndpoint(u.strip()) for u in urls if u and u.strip()]
        self._max_failures = max_failures
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._idx = 0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, var: str = "WST_PROXY_URLS", **kwargs: Any) -> "ProxyPool":
        raw = os.environ.get(var, "")
        return cls([p for p in raw.replace("\n", ",").split(",") if p.strip()], **kwargs)

    def __bool__(self) -> bool:
        return bool(self._proxies)

    def acquire(self) -> ProxyEndpoint | None:
        with self._lock:
            if not self._proxies:
                return None
            now = self._clock()
            for _ in range(len(self._proxies)):
                proxy = self._proxies[self._idx % len(self._proxies)]
                self._idx += 1
                if proxy.cooldown_until <= now:
                    return proxy
            return None

    def report(self, proxy: ProxyEndpoint | None, ok: bool) -> None:
        if proxy is None:
            return
        with self._lock:
            if ok:
                proxy.successes += 1
                proxy.failures = 0
            else:
                proxy.failures += 1
                if proxy.failures >= self._max_failures:
                    proxy.cooldown_until = self._clock() + self._cooldown_s
                    proxy.failures = 0

    def stats(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{"proxy": p.label, "successes": p.successes, "failures": p.failures,
                     "cooling_down": p.cooldown_until > self._clock()} for p in self._proxies]


@dataclass
class CrawlSession:
    session_id: str
    cookie_jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)
    proxy: ProxyEndpoint | None = None
    usage_count: int = 0
    error_score: float = 0.0
    retired: bool = False
    warmed_up: set = field(default_factory=set)

    def cookies_for(self, domain: str) -> dict[str, str]:
        return {c.name: c.value for c in self.cookie_jar if domain.endswith(c.domain.lstrip("."))}

    def set_cookie(self, domain: str, name: str, value: str, path: str = "/") -> None:
        self.cookie_jar.set_cookie(http.cookiejar.Cookie(
            0, name, value, None, False, domain, True, domain.startswith("."), path, True,
            False, None, False, None, None, {}))


class SessionPool:
    """Crawlee-style session pool: cookie jars bound to proxies, retired on blocks."""

    def __init__(self, *, max_pool_size: int = 4, max_usage: int = 50, max_error_score: float = 3.0,
                 proxy_pool: ProxyPool | None = None) -> None:
        self.max_pool_size = max_pool_size
        self.max_usage = max_usage
        self.max_error_score = max_error_score
        self.proxy_pool = proxy_pool or ProxyPool()
        self._sessions: list[CrawlSession] = []
        self._counter = 0
        self._lock = threading.Lock()

    def _new(self) -> CrawlSession:
        self._counter += 1
        session = CrawlSession(session_id=f"session-{self._counter}", proxy=self.proxy_pool.acquire())
        self._sessions.append(session)
        return session

    def get(self, session_id: str = "") -> CrawlSession:
        with self._lock:
            if session_id:
                for s in self._sessions:
                    if s.session_id == session_id and not s.retired:
                        return s
            live = [s for s in self._sessions if not s.retired and s.usage_count < self.max_usage]
            if len(live) < self.max_pool_size:
                return self._new()
            return min(live, key=lambda s: s.usage_count)

    def import_cookies(self, domain: str, cookies: dict[str, str]) -> CrawlSession:
        """Attach operator-supplied (authorized) cookies to a fresh session."""
        with self._lock:
            session = self._new()
        for name, value in cookies.items():
            session.set_cookie(domain, name, value)
        return session

    def mark_good(self, session: CrawlSession) -> None:
        with self._lock:
            session.usage_count += 1
            session.error_score = max(0.0, session.error_score - 0.5)
        self.proxy_pool.report(session.proxy, True)

    def mark_bad(self, session: CrawlSession, *, blocked: bool = False) -> None:
        with self._lock:
            session.usage_count += 1
            session.error_score += 3.0 if blocked else 1.0
            if session.error_score >= self.max_error_score:
                session.retired = True
        self.proxy_pool.report(session.proxy, False)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"sessions": len(self._sessions), "retired": sum(s.retired for s in self._sessions),
                    "proxies": self.proxy_pool.stats()}


# --------------------------------------------------------------------------
# Throttle and retry
# --------------------------------------------------------------------------
class DomainThrottle:
    """Per-domain politeness delay with jitter and AutoThrottle-style adaptation."""

    def __init__(self, *, min_delay: float = 1.0, max_delay: float = 60.0, jitter: float = 0.5,
                 target_concurrency: float = 1.0, autothrottle: bool = True,
                 clock: Callable[[], float] = time.monotonic, sleeper: Callable[[float], None] = time.sleep,
                 rng: Callable[[], float] = random.random) -> None:
        self.min_delay, self.max_delay, self.jitter = min_delay, max_delay, jitter
        self.target_concurrency, self.autothrottle = target_concurrency, autothrottle
        self._clock, self._sleep, self._rng = clock, sleeper, rng
        self._next_allowed: dict[str, float] = {}
        self._delay: dict[str, float] = {}
        self._lock = threading.Lock()

    def delay_for(self, domain: str) -> float:
        return self._delay.get(domain, self.min_delay)

    def wait(self, domain: str) -> float:
        with self._lock:
            now = self._clock()
            ready = self._next_allowed.get(domain, now)
            wait = max(0.0, ready - now)
            delay = self.delay_for(domain)
            factor = 1.0 + (self._rng() * 2 - 1) * self.jitter if self.jitter else 1.0
            self._next_allowed[domain] = max(now, ready) + delay * factor
        if wait > 0:
            self._sleep(wait)
        return wait

    def record_latency(self, domain: str, latency_s: float, status: int | None) -> None:
        if not self.autothrottle:
            return
        with self._lock:
            current = self.delay_for(domain)
            target = latency_s / max(self.target_concurrency, 0.1)
            new = (current + target) / 2.0
            if status is not None and (status >= 500 or status == 429):
                new = max(new, current)  # never speed up on errors
            self._delay[domain] = min(self.max_delay, max(self.min_delay, new))

    def penalize(self, domain: str, retry_after: float | None = None) -> None:
        with self._lock:
            current = self.delay_for(domain)
            self._delay[domain] = min(self.max_delay, max(current * 2, retry_after or 0.0, self.min_delay))
            if retry_after:
                self._next_allowed[domain] = self._clock() + retry_after


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    retry_http_codes: frozenset = RETRY_HTTP_CODES
    base_delay: float = 0.5
    max_delay: float = 10.0

    def backoff(self, attempt: int) -> float:
        """Exponential backoff with ceiling (XueQiu TimeWaitingStrategy, off-by-one fixed)."""
        return min(self.max_delay, self.base_delay * (2 ** max(0, attempt)))

    def should_retry(self, req: CrawlRequest, status: int | None, error: str) -> bool:
        limit = self.max_retries if req.max_retries is None else req.max_retries
        if req.retry_count >= limit:
            return False
        if error:
            return True
        return status in self.retry_http_codes


# --------------------------------------------------------------------------
# Fetchers
# --------------------------------------------------------------------------
@dataclass
class FetchResponse:
    url: str
    status: int | None
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    elapsed_s: float = 0.0
    error: str = ""
    fetcher: str = "static"

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8", errors="replace")).hexdigest()


class Fetcher(Protocol):
    name: str

    def __call__(self, request: CrawlRequest, session: CrawlSession, timeout: float) -> FetchResponse: ...


class UrllibFetcher:
    """Static HTTP fetch with the session's cookie jar and (optional) proxy."""

    name = "static"

    def __init__(self, *, user_agent: str = "wallstreet-tieling-crawler/0.6 (+due-diligence)") -> None:
        self.user_agent = user_agent

    def __call__(self, request: CrawlRequest, session: CrawlSession, timeout: float) -> FetchResponse:
        handlers: list[Any] = [urllib.request.HTTPCookieProcessor(session.cookie_jar)]
        if session.proxy is not None:
            handlers.append(urllib.request.ProxyHandler({"http": session.proxy.url, "https": session.proxy.url}))
        opener = urllib.request.build_opener(*handlers)
        headers = {"User-Agent": self.user_agent, **request.headers}
        data = request.body.encode() if request.body else None
        req = urllib.request.Request(request.url, data=data, headers=headers, method=request.method)
        start = time.monotonic()
        try:
            with opener.open(req, timeout=timeout) as resp:
                body = resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
                return FetchResponse(resp.geturl(), resp.status, dict(resp.headers.items()), body,
                                     time.monotonic() - start, fetcher=self.name)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return FetchResponse(request.url, exc.code, dict(exc.headers.items()) if exc.headers else {}, body,
                                 time.monotonic() - start, fetcher=self.name)
        except Exception as exc:
            return FetchResponse(request.url, None, {}, "", time.monotonic() - start,
                                 error=f"{type(exc).__name__}: {exc}", fetcher=self.name)


class AdaptiveFetcher:
    """Scrapling-style ladder: try cheap fetchers first, escalate when needed.

    ``needs_escalation`` decides when a response is an empty JS shell. Escalation
    targets are operator-provided fetchers (e.g. a Playwright renderer for an
    authorized session); challenge pages are NOT escalated — they are handoffs.
    """

    name = "adaptive"

    def __init__(self, fetchers: list[Callable[..., FetchResponse]],
                 needs_escalation: Callable[[FetchResponse], bool] | None = None) -> None:
        if not fetchers:
            raise ValueError("AdaptiveFetcher needs at least one fetcher")
        self.fetchers = fetchers
        self.needs_escalation = needs_escalation or _looks_like_js_shell

    def __call__(self, request: CrawlRequest, session: CrawlSession, timeout: float) -> FetchResponse:
        response = self.fetchers[0](request, session, timeout)
        for fetcher in self.fetchers[1:]:
            if detect_challenge(response) or not self.needs_escalation(response):
                break
            response = fetcher(request, session, timeout)
        return response


def _looks_like_js_shell(resp: FetchResponse) -> bool:
    if resp.status != 200:
        return False
    text = resp.body.lower()
    return len(text.strip()) < 512 or ("<noscript" in text and "enable javascript" in text)


def detect_challenge(resp: FetchResponse) -> bool:
    if resp.status in BLOCK_HTTP_CODES:
        return True
    head = resp.body[:4000].lower()
    return any(marker in head for marker in CHALLENGE_MARKERS) and (resp.status in {200, 403, 429, 503} or resp.status is None)


# --------------------------------------------------------------------------
# Pipeline stages
# --------------------------------------------------------------------------
@dataclass
class MapperOutput:
    items: list[dict[str, Any]] = field(default_factory=list)
    requests: list[CrawlRequest] = field(default_factory=list)


Mapper = Callable[[CrawlRequest, FetchResponse], MapperOutput]
ItemPipeline = Callable[[dict[str, Any], "CrawlContext"], "dict[str, Any] | None"]


@dataclass
class CrawlContext:
    run_id: str
    request: CrawlRequest
    response: FetchResponse
    session_id: str
    proxy: str


class CrawlRun:
    """Collector -> Mapper -> Consumer engine with first-class run ledger."""

    def __init__(
        self,
        *,
        name: str,
        mappers: dict[str, Mapper],
        item_pipelines: list[ItemPipeline] | None = None,
        fetcher: Callable[..., FetchResponse] | None = None,
        queue: RequestQueue | None = None,
        session_pool: SessionPool | None = None,
        throttle: DomainThrottle | None = None,
        retry: RetryPolicy | None = None,
        obey_robots: bool = True,
        robots_checker: Callable[[str, str], bool] | None = None,
        allowed_domains: Iterable[str] = (),
        max_depth: int = 3,
        timeout_s: float = 30.0,
        checkpoint_path: str | Path | None = None,
        checkpoint_every: int = 25,
        warmup_urls: dict[str, str] | None = None,
        source_type: str = "crawler_public_page",
    ) -> None:
        self.name = name
        self.mappers = mappers
        self.item_pipelines = item_pipelines or [standardize_item]
        self.fetcher = fetcher or UrllibFetcher()
        self.queue = queue or RequestQueue()
        self.sessions = session_pool or SessionPool()
        self.throttle = throttle or DomainThrottle()
        self.retry = retry or RetryPolicy()
        self.obey_robots = obey_robots
        self._robots_checker = robots_checker or _RobotsCache().allowed
        self.allowed_domains = {d.lower() for d in allowed_domains}
        self.max_depth = max_depth
        self.timeout_s = timeout_s
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
        self.checkpoint_every = checkpoint_every
        self.warmup_urls = warmup_urls or {}
        self.source_type = source_type
        self.started_at = utc_now()
        self.finished_at = ""
        self.run_id = "crawl-" + hashlib.sha256(f"{name}|{self.started_at}|{id(self)}".encode()).hexdigest()[:16]
        self.records: list[dict[str, Any]] = []
        self.gaps: list[dict[str, Any]] = []
        self.counters: dict[str, int] = {"fetched": 0, "retried": 0, "items": 0, "dropped_items": 0,
                                         "robots_blocked": 0, "handoffs": 0, "failed": 0, "offsite": 0}
        self._lock = threading.Lock()
        self._handled_since_checkpoint = 0

    # ---- Collector ---------------------------------------------------
    def collect(self, seeds: Iterable[CrawlRequest | str]) -> int:
        return self.queue.add_many(seeds)

    # ---- main loop ---------------------------------------------------
    def run(self, *, max_requests: int = 100, concurrency: int = 4,
            idle_sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
        processed = 0
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            while processed < max_requests and not self.queue.is_finished():
                batch: list[CrawlRequest] = []
                while len(batch) < concurrency and processed + len(batch) < max_requests:
                    req = self.queue.fetch_next()
                    if req is None:
                        break
                    batch.append(req)
                if not batch:
                    wait = self.queue.next_ready_in()
                    if wait is None:
                        break
                    idle_sleep(min(wait, 5.0))
                    continue
                list(pool.map(self._process, batch))
                processed += len(batch)
        self.finished_at = utc_now()
        if self.checkpoint_path:
            self.queue.save(self.checkpoint_path)
        for req in self.queue.requests("pending"):
            self._gap(req, "not_processed_within_budget", f"max_requests={max_requests}")
        return self.summary()

    def _process(self, req: CrawlRequest) -> None:
        if self.allowed_domains and not any(req.domain == d or req.domain.endswith("." + d) for d in self.allowed_domains):
            self._count("offsite")
            self.queue.mark_failed(req, "offsite", state="failed")
            return
        if self.obey_robots and not self._robots_checker(req.url, getattr(self.fetcher, "user_agent", "*")):
            self._count("robots_blocked")
            self.queue.mark_failed(req, "robots_txt_disallowed")
            self._gap(req, "robots_txt_disallowed", "")
            return
        session = self.sessions.get(req.session_id)
        req.session_id = session.session_id
        self._warm_up(session, req)
        self.throttle.wait(req.domain)
        response = self.fetcher(req, session, self.timeout_s)
        self._count("fetched")
        self.throttle.record_latency(req.domain, response.elapsed_s, response.status)
        if detect_challenge(response):
            self.sessions.mark_bad(session, blocked=True)
            self._count("handoffs")
            self.queue.mark_failed(req, f"challenge_or_block status={response.status}", state="handoff")
            self._gap(req, "human_verification_required",
                      f"status={response.status}; provide an authorized session/cookies or a licensed provider",
                      response=response)
            return
        if response.error or (response.status is not None and response.status >= 400):
            self.sessions.mark_bad(session)
            if response.status == 429:
                self.throttle.penalize(req.domain, _retry_after(response.headers))
            if self.retry.should_retry(req, response.status, response.error):
                self._count("retried")
                self.queue.reclaim(req, delay=self.retry.backoff(req.retry_count),
                                   error=response.error or f"http_{response.status}")
                return
            self._count("failed")
            self.queue.mark_failed(req, response.error or f"http_{response.status}")
            self._gap(req, "fetch_failed", response.error or f"http_{response.status}", response=response)
            return
        self.sessions.mark_good(session)
        mapper = self.mappers.get(req.label) or self.mappers.get("")
        if mapper is None:
            self.queue.mark_failed(req, f"no_mapper_for_label:{req.label}")
            self._gap(req, "no_mapper", req.label, response=response)
            return
        try:
            out = mapper(req, response)
        except Exception as exc:
            self.queue.mark_failed(req, f"mapper_error:{type(exc).__name__}")
            self._gap(req, "parse_error", f"{type(exc).__name__}: {exc}", response=response)
            return
        ctx = CrawlContext(self.run_id, req, response, session.session_id,
                           session.proxy.label if session.proxy else "")
        for item in out.items:
            self._consume(item, ctx)
        for child in out.requests:
            if child.depth == 0:
                child.depth = req.depth + 1
            if child.depth <= self.max_depth:
                if not child.session_id:
                    child.session_id = session.session_id
                self.queue.add(child)
        self.queue.mark_handled(req)
        self._maybe_checkpoint()

    def _warm_up(self, session: CrawlSession, req: CrawlRequest) -> None:
        """Visit a configured landing page once per session/domain (XueQiu updateCookie)."""
        url = self.warmup_urls.get(req.domain)
        if not url or req.domain in session.warmed_up:
            return
        session.warmed_up.add(req.domain)
        self.throttle.wait(req.domain)
        self.fetcher(CrawlRequest(url=url, label="__warmup__"), session, self.timeout_s)

    # ---- Consumer ----------------------------------------------------
    def _consume(self, item: dict[str, Any], ctx: CrawlContext) -> None:
        current: dict[str, Any] | None = dict(item)
        for stage in self.item_pipelines:
            current = stage(current, ctx)
            if current is None:
                self._count("dropped_items")
                return
        current.setdefault("source_type", self.source_type)
        with self._lock:
            self.records.append(current)
            self.counters["items"] += 1

    def _maybe_checkpoint(self) -> None:
        if not self.checkpoint_path:
            return
        with self._lock:
            self._handled_since_checkpoint += 1
            due = self._handled_since_checkpoint >= self.checkpoint_every
            if due:
                self._handled_since_checkpoint = 0
        if due:
            self.queue.save(self.checkpoint_path)

    def _count(self, key: str) -> None:
        with self._lock:
            self.counters[key] = self.counters.get(key, 0) + 1

    def _gap(self, req: CrawlRequest, reason: str, detail: str, *, response: FetchResponse | None = None) -> None:
        with self._lock:
            self.gaps.append({
                "source_name": f"crawler_{self.name}",
                "source_type": "crawl_evidence_gap",
                "source_hint": f"crawler_{self.name}",
                "record_type": "crawl_evidence_gap",
                "entity": req.user_data.get("entity") or req.url,
                "title": f"{reason}: {req.url}",
                "summary": f"{reason}; {detail}".strip("; "),
                "url": req.url,
                "retrieved_at": utc_now(),
                "confidence": 0.0,
                "gap": {"reason": reason, "detail": detail, "retry_count": req.retry_count,
                        "errors": list(req.errors), "http_status": response.status if response else None,
                        "absence_is_not_proof": True},
                "evidence": [{"type": "crawl_attempt", "run_id": self.run_id, "source_url": req.url,
                              "fetcher": response.fetcher if response else "", "manual_review_required": True}],
            })

    # ---- outputs -----------------------------------------------------
    def summary(self) -> dict[str, Any]:
        return {
            "type": "crawl_run",
            "run_id": self.run_id,
            "name": self.name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "queue": self.queue.stats(),
            "counters": dict(self.counters),
            "sessions": self.sessions.stats(),
            "throttle": {d: round(self.throttle.delay_for(d), 3) for d in {r.domain for r in self.queue.requests()}},
            "record_count": len(self.records),
            "gap_count": len(self.gaps),
        }

    def standardized_records(self) -> list[dict[str, Any]]:
        run_record = {
            "source_name": f"crawler_{self.name}",
            "source_type": "crawl_run",
            "source_hint": f"crawler_{self.name}",
            "record_type": "crawl_run",
            "entity": self.name,
            "title": f"crawl run {self.name}",
            "summary": json.dumps(self.counters, ensure_ascii=False, sort_keys=True),
            "url": "",
            "retrieved_at": self.finished_at or self.started_at,
            "confidence": 1.0,
            "run": self.summary(),
            "evidence": [{"type": "crawl_run", "run_id": self.run_id}],
        }
        return [run_record, *self.records, *self.gaps]


def standardize_item(item: dict[str, Any] | None, ctx: CrawlContext) -> dict[str, Any] | None:
    """Default Consumer stage: attach provenance and the standardized record shape."""
    if item is None:
        return None
    record = dict(item)
    record.setdefault("source_name", f"crawler_{ctx.request.label or 'page'}")
    record.setdefault("source_hint", record["source_name"])
    record.setdefault("record_type", "crawled_item")
    record.setdefault("url", ctx.response.url or ctx.request.url)
    record.setdefault("retrieved_at", utc_now())
    record.setdefault("confidence", 0.6)
    if not any(str(record.get(k) or "").strip() for k in ("entity", "title", "summary")):
        record["title"] = record["url"]
    provenance = {
        "type": "crawl_fetch",
        "run_id": ctx.run_id,
        "source_url": ctx.response.url or ctx.request.url,
        "http_status": ctx.response.status,
        "fetcher": ctx.response.fetcher,
        "content_sha256": ctx.response.content_sha256,
        "session_id": ctx.session_id,
        "proxy": ctx.proxy,
        "depth": ctx.request.depth,
        "request_unique_key": ctx.request.unique_key,
    }
    record["evidence"] = [*list(record.get("evidence") or []), provenance]
    return record


def dedupe_items(key_fields: tuple[str, ...]) -> ItemPipeline:
    """Item pipeline stage that drops repeated items by key fields (Scrapy DropItem)."""
    seen: set[tuple[Any, ...]] = set()
    lock = threading.Lock()

    def stage(item: dict[str, Any] | None, ctx: CrawlContext) -> dict[str, Any] | None:
        if item is None:
            return None
        key = tuple(item.get(f) for f in key_fields)
        if all(k in (None, "") for k in key):
            return item  # nothing to dedupe on
        with lock:
            if key in seen:
                return None
            seen.add(key)
        return item

    return stage


def require_fields(*fields: str) -> ItemPipeline:
    def stage(item: dict[str, Any] | None, ctx: CrawlContext) -> dict[str, Any] | None:
        if item is None or any(item.get(f) in (None, "") for f in fields):
            return None
        return item

    return stage


class _RobotsCache:
    def __init__(self, fetch_timeout: float = 10.0) -> None:
        self._parsers: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._timeout = fetch_timeout
        self._lock = threading.Lock()

    def allowed(self, url: str, user_agent: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            parser = self._parsers.get(base, False)
        if parser is False:
            parser = urllib.robotparser.RobotFileParser(base + "/robots.txt")
            try:
                with urllib.request.urlopen(base + "/robots.txt", timeout=self._timeout) as resp:
                    parser.parse(resp.read().decode("utf-8", errors="replace").splitlines())
            except Exception:
                parser = None  # unreachable robots.txt -> allow (RFC 9309 §2.3.1.3 for 4xx)
            with self._lock:
                self._parsers[base] = parser
        return True if parser is None else parser.can_fetch(user_agent or "*", url)


def _retry_after(headers: dict[str, str]) -> float | None:
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return float(v)
            except ValueError:
                return None
    return None


__all__ = [
    "AdaptiveFetcher", "CrawlContext", "CrawlRequest", "CrawlRun", "CrawlSession", "DomainThrottle",
    "FetchResponse", "MapperOutput", "ProxyPool", "RequestQueue", "RetryPolicy", "SessionPool",
    "UrllibFetcher", "dedupe_items", "detect_challenge", "require_fields", "standardize_item", "unique_key_for",
]
