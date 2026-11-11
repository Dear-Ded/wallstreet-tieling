#!/usr/bin/env python3
"""Crawler runtime: queue, sessions, proxies, throttle, retry, checkpoints, pipelines."""
from __future__ import annotations

import json

from core.crawl_presets import build_site_crawl, build_xueqiu_run, xueqiu_symbol
from core.crawl_runtime import (
    AdaptiveFetcher,
    CrawlRequest,
    CrawlRun,
    DomainThrottle,
    FetchResponse,
    MapperOutput,
    ProxyPool,
    RequestQueue,
    RetryPolicy,
    SessionPool,
    detect_challenge,
    require_fields,
    standardize_item,
    unique_key_for,
)
from core.record_quality import audit_standardized_records


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def fast_throttle(clock: Clock) -> DomainThrottle:
    return DomainThrottle(min_delay=0.0, jitter=0.0, clock=clock, sleeper=clock.sleep, autothrottle=False)


class ScriptedFetcher:
    user_agent = "test"

    def __init__(self, script: dict[str, list[FetchResponse]]) -> None:
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, request, session, timeout):
        self.calls.append((request.url, session.session_id, session.proxy.label if session.proxy else ""))
        queue = self.script.get(request.url) or [FetchResponse(request.url, 200, {}, "{}")]
        return queue.pop(0) if len(queue) > 1 else queue[0]


def test_unique_key_normalizes_and_queue_dedupes() -> None:
    assert unique_key_for("HTTPS://Example.COM/a?b=2&a=1#frag") == unique_key_for("https://example.com/a?a=1&b=2")
    q = RequestQueue()
    assert q.add("https://example.com/a?a=1&b=2") is True
    assert q.add("https://EXAMPLE.com/a?b=2&a=1") is False
    assert q.stats() == {"total": 1, "pending": 1}


def test_checkpoint_roundtrip_is_json_and_resumes_in_progress(tmp_path) -> None:
    q = RequestQueue()
    q.add_many(["https://example.com/1", "https://example.com/2", "https://example.com/3"])
    first = q.fetch_next()
    q.mark_handled(first)
    q.fetch_next()  # left in_progress (simulated crash)
    path = q.save(tmp_path / "ckpt" / "queue.json")
    data = json.loads(path.read_text())
    assert data["type"] == "crawl_queue_checkpoint"
    resumed = RequestQueue.load(path)
    assert resumed.stats() == {"total": 3, "handled": 1, "pending": 2}


def test_proxy_pool_rotation_and_cooldown() -> None:
    clock = Clock()
    pool = ProxyPool(["http://p1:8080", "http://p2:8080"], max_failures=2, cooldown_s=60, clock=clock)
    a, b = pool.acquire(), pool.acquire()
    assert {a.label, b.label} == {"http://p1:8080", "http://p2:8080"}
    pool.report(a, False)
    pool.report(a, False)
    assert all(pool.acquire() is b for _ in range(3))
    clock.t = 61
    assert {pool.acquire().label for _ in range(2)} == {"http://p1:8080", "http://p2:8080"}
    assert not ProxyPool([])


def test_proxy_pool_from_env(monkeypatch) -> None:
    monkeypatch.setenv("WST_PROXY_URLS", "http://a:1, http://b:2")
    assert [p["proxy"] for p in ProxyPool.from_env().stats()] == ["http://a:1", "http://b:2"]


def test_session_pool_retires_blocked_sessions_and_imports_cookies() -> None:
    pool = SessionPool(max_pool_size=1, max_error_score=3.0, proxy_pool=ProxyPool(["http://p1:1"]))
    s1 = pool.get()
    assert s1.proxy.label == "http://p1:1"
    pool.mark_bad(s1, blocked=True)
    assert s1.retired
    s2 = pool.get()
    assert s2.session_id != s1.session_id
    authorized = pool.import_cookies("xueqiu.com", {"xq_a_token": "operator-supplied"})
    assert authorized.cookies_for("xueqiu.com") == {"xq_a_token": "operator-supplied"}


def test_throttle_spacing_jitter_and_autothrottle() -> None:
    clock = Clock()
    t = DomainThrottle(min_delay=1.0, max_delay=10.0, jitter=0.0, clock=clock, sleeper=clock.sleep)
    assert t.wait("a.com") == 0
    assert t.wait("a.com") == 1.0
    assert t.wait("b.com") == 0
    t.record_latency("a.com", 6.0, 200)
    assert t.delay_for("a.com") == 3.5
    t.penalize("a.com", retry_after=8)
    assert t.delay_for("a.com") == 8


def test_retry_backoff_bounded() -> None:
    p = RetryPolicy(max_retries=2, base_delay=0.5, max_delay=3)
    assert [p.backoff(i) for i in range(4)] == [0.5, 1.0, 2.0, 3]
    r = CrawlRequest(url="https://x")
    assert p.should_retry(r, 503, "") and not p.should_retry(r, 404, "")
    r.retry_count = 2
    assert not p.should_retry(r, 503, "")


def test_challenge_detection() -> None:
    assert detect_challenge(FetchResponse("u", 403, {}, "forbidden"))
    assert detect_challenge(FetchResponse("u", 200, {}, "<html>请完成安全验证 captcha</html>"))
    assert not detect_challenge(FetchResponse("u", 200, {}, "<html>ok</html>"))


def _mapper(req, resp):
    data = json.loads(resp.body or "{}")
    out = MapperOutput(items=[{"entity": data.get("name", ""), "title": data.get("name", ""), "value": data.get("v")}])
    out.requests = [CrawlRequest(url=u, label="") for u in data.get("next", [])]
    return out


def test_crawl_run_retries_handoffs_gaps_and_provenance(tmp_path) -> None:
    clock = Clock()
    fetcher = ScriptedFetcher({
        "https://ex.com/a": [FetchResponse("https://ex.com/a", 200, {}, json.dumps({"name": "A", "v": 1, "next": ["https://ex.com/b", "https://ex.com/c", "https://other.com/x"]}))],
        "https://ex.com/b": [FetchResponse("https://ex.com/b", 503, {}, ""), FetchResponse("https://ex.com/b", 200, {}, json.dumps({"name": "B", "v": 2}))],
        "https://ex.com/c": [FetchResponse("https://ex.com/c", 200, {}, "<html>captcha 滑块</html>")],
    })
    run = CrawlRun(name="t", mappers={"": _mapper}, fetcher=fetcher, throttle=fast_throttle(clock),
                   retry=RetryPolicy(max_retries=2, base_delay=0.0), obey_robots=False, allowed_domains=["ex.com"],
                   session_pool=SessionPool(proxy_pool=ProxyPool(["http://p1:1"])),
                   checkpoint_path=tmp_path / "q.json", checkpoint_every=1)
    run.collect(["https://ex.com/a"])
    summary = run.run(max_requests=20, concurrency=2, idle_sleep=clock.sleep)
    assert summary["counters"]["retried"] == 1
    assert summary["counters"]["handoffs"] == 1
    assert summary["counters"]["offsite"] == 1
    assert summary["queue"]["handled"] == 2
    records = run.standardized_records()
    assert audit_standardized_records(records).ok
    assert records[0]["record_type"] == "crawl_run"
    items = [r for r in records if r["record_type"] == "crawled_item"]
    assert {r["title"] for r in items} == {"A", "B"}
    prov = items[0]["evidence"][-1]
    assert prov["content_sha256"] and prov["proxy"] == "http://p1:1" and prov["run_id"] == run.run_id
    gaps = [r for r in records if r["record_type"] == "crawl_evidence_gap"]
    assert [g["gap"]["reason"] for g in gaps] == ["human_verification_required"]
    assert json.loads((tmp_path / "q.json").read_text())["type"] == "crawl_queue_checkpoint"


def test_failures_after_retries_become_gaps_and_budget_leftovers_are_gaps() -> None:
    clock = Clock()
    fetcher = ScriptedFetcher({"https://ex.com/a": [FetchResponse("https://ex.com/a", 500, {}, "")]})
    run = CrawlRun(name="t", mappers={"": _mapper}, fetcher=fetcher, throttle=fast_throttle(clock),
                   retry=RetryPolicy(max_retries=1, base_delay=0.0), obey_robots=False)
    run.collect(["https://ex.com/a", "https://ex.com/z"])
    run.run(max_requests=2, concurrency=1, idle_sleep=clock.sleep)
    reasons = sorted(g["gap"]["reason"] for g in run.gaps)
    assert reasons == ["fetch_failed", "not_processed_within_budget"]


def test_robots_disallow_is_respected() -> None:
    clock = Clock()
    run = CrawlRun(name="t", mappers={"": _mapper}, fetcher=ScriptedFetcher({}), throttle=fast_throttle(clock),
                   robots_checker=lambda url, ua: not url.endswith("/private"))
    run.collect(["https://ex.com/private"])
    run.run(max_requests=5, idle_sleep=clock.sleep)
    assert run.counters["robots_blocked"] == 1
    assert run.gaps[0]["gap"]["reason"] == "robots_txt_disallowed"


def test_item_pipeline_drops_and_standardizes() -> None:
    clock = Clock()
    fetcher = ScriptedFetcher({"https://ex.com/a": [FetchResponse("https://ex.com/a", 200, {}, json.dumps({"name": "", "v": 1}))]})
    run = CrawlRun(name="t", mappers={"": _mapper}, fetcher=fetcher, throttle=fast_throttle(clock), obey_robots=False,
                   item_pipelines=[require_fields("entity"), standardize_item])
    run.collect(["https://ex.com/a"])
    run.run(idle_sleep=clock.sleep)
    assert run.counters["dropped_items"] == 1 and run.records == []


def test_adaptive_fetcher_escalates_js_shell_but_not_challenges() -> None:
    calls = []

    def static(req, session, timeout):
        calls.append("static")
        return FetchResponse(req.url, 200, {}, "<noscript>Please enable JavaScript</noscript>")

    def rendered(req, session, timeout):
        calls.append("rendered")
        return FetchResponse(req.url, 200, {}, "<html>" + "x" * 600 + "</html>", fetcher="rendered")

    fetch = AdaptiveFetcher([static, rendered])
    resp = fetch(CrawlRequest(url="https://ex.com"), SessionPool().get(), 5)
    assert resp.fetcher == "rendered" and calls == ["static", "rendered"]

    calls.clear()

    def challenged(req, session, timeout):
        calls.append("static")
        return FetchResponse(req.url, 403, {}, "captcha")

    AdaptiveFetcher([challenged, rendered])(CrawlRequest(url="https://ex.com"), SessionPool().get(), 5)
    assert calls == ["static"]


def test_xueqiu_preset_warmup_quote_and_discussion_pages() -> None:
    assert xueqiu_symbol("600519") == "SH600519" and xueqiu_symbol("000001") == "SZ000001"
    assert xueqiu_symbol("830799") == "BJ830799" and xueqiu_symbol("AAPL") == "AAPL"
    quote = {"data": {"quote": {"symbol": "SH600519", "name": "贵州茅台", "current": 1500.0, "percent": 1.2,
                                "market_capital": 1.9e12, "pe_ttm": 25.1}}, "error_code": 0}
    page1 = {"list": [{"id": 11, "user_id": 7, "text": "<p>茅台 年报</p>", "created_at": 1700000000000,
                       "user": {"id": 7, "screen_name": "价值投资者", "followers_count": 1234, "province": "上海"}}]}
    page2 = {"list": [{"id": 12, "user_id": 8, "text": "回复", "user": {"id": 8, "screen_name": "b"}}]}
    clock = Clock()
    fetcher = ScriptedFetcher({
        "https://stock.xueqiu.com/v5/stock/quote.json?symbol=SH600519&extend=detail": [FetchResponse("q", 200, {}, json.dumps(quote))],
        "https://xueqiu.com/query/v1/symbol/search/status.json?symbol=SH600519&count=20&page=1&sort=time": [FetchResponse("d1", 200, {}, json.dumps(page1))],
        "https://xueqiu.com/query/v1/symbol/search/status.json?symbol=SH600519&count=20&page=2&sort=time": [FetchResponse("d2", 200, {}, json.dumps(page2))],
    })
    run = build_xueqiu_run(["600519"], entity="贵州茅台酒股份有限公司", discussion_pages=2, fetcher=fetcher,
                           throttle=fast_throttle(clock))
    run.run(max_requests=10, concurrency=1, idle_sleep=clock.sleep)
    warmups = [c for c in fetcher.calls if c[0] == "https://xueqiu.com/"]
    assert len(warmups) == 2  # one per session x domain (stock.xueqiu.com, xueqiu.com)
    records = run.standardized_records()
    assert audit_standardized_records(records).ok
    snap = next(r for r in records if r["record_type"] == "market_quote_snapshot")
    assert snap["fields"]["pe_ttm"] == 25.1 and snap["entity"] == "贵州茅台酒股份有限公司"
    posts = [r for r in records if r["record_type"] == "public_opinion_post"]
    assert len(posts) == 2
    assert posts[0]["author"]["screen_name"] == "价值投资者" and posts[0]["author"]["province"] == "上海"
    assert posts[0]["url"] == "https://xueqiu.com/7/11"


def test_site_crawl_preset_extracts_contacts_and_stays_on_site() -> None:
    clock = Clock()
    home = ('<html><title>Demo Co</title><meta name="description" content="Demo maker">'
            '<a href="/about">a</a><a href="https://partner.example/x">p</a> sales@example.invalid 021-55501234</html>')
    fetcher = ScriptedFetcher({"https://demo.example/": [FetchResponse("https://demo.example/", 200, {}, home)],
                               "https://demo.example/about": [FetchResponse("https://demo.example/about", 200, {}, "<title>About</title>")]})
    run = build_site_crawl(["https://demo.example/"], entity="Demo Co", fetcher=fetcher, throttle=fast_throttle(clock),
                           obey_robots=False)
    run.run(max_requests=10, idle_sleep=clock.sleep)
    pages = [r for r in run.standardized_records() if r["record_type"] == "public_web_page"]
    assert {p["title"] for p in pages} == {"Demo Co", "About"}
    home_rec = next(p for p in pages if p["title"] == "Demo Co")
    assert home_rec["page"]["emails"] == ["sales@example.invalid"]
    assert "021-55501234" in home_rec["page"]["phones"]
    assert home_rec["page"]["external_domains"] == ["partner.example"]
