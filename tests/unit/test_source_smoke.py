"""Boundary tests for source smoke and public archive access."""
from __future__ import annotations

from adapters.public_archive_access import PublicArchiveAccess
from adapters.source_smoke_harness import SmokeStatus, SourceSmokeHarness


def _fake_http_get(url: str) -> tuple[int, str | None, str]:
    if "definitely-not-a-real-domain" in url and "web.archive.org" not in url:
        return 0, None, "dns failure"
    return 200, "Unified Social Credit Code Administrative Penalty Demo public page", ""


def _fake_authorized_get(url: str, credentials: dict) -> tuple[int, str | None, str]:
    return 200, '{"status":"ok","records":1}', ""


def _fake_fetch_url(url: str) -> tuple[int, str | None, str]:
    return 200, "Unified Social Credit Code Administrative Penalty Demo archive page", ""


def _no_sleep(seconds: float) -> None:
    return None


def test_public_source_smoke_produces_trace() -> None:
    harness = SourceSmokeHarness(http_get=_fake_http_get)

    trace = harness.public_source_smoke(
        "creditchina",
        "https://www.creditchina.gov.cn/search?keyword=test",
    )

    assert trace.source_category.value == "public"
    assert trace.source_name == "creditchina"
    assert trace.access_method == "standard_http_get"
    assert trace.trace_id
    assert trace.timestamp
    assert trace.status == SmokeStatus.LIVE_VERIFIED
    assert trace.field_count >= 1


def test_authorized_source_smoke_without_credentials() -> None:
    harness = SourceSmokeHarness(authorized_get=_fake_authorized_get)

    trace = harness.authorized_source_smoke("qyyjt", "https://api.example.com", credentials=None)

    assert trace.status == SmokeStatus.CONFIG_REQUIRED
    assert trace.source_category.value == "authorized"


def test_authorized_source_smoke_with_credentials_redacts_secret() -> None:
    harness = SourceSmokeHarness(authorized_get=_fake_authorized_get)

    trace = harness.authorized_source_smoke(
        "test_api",
        "https://httpbin.org/get",
        credentials={"auth_token": "test_token_12345"},
    )

    trace_str = str(trace.to_dict())
    assert trace.status == SmokeStatus.LIVE_VERIFIED
    assert "test_token_12345" not in trace_str


def test_smoke_report_aggregates_correctly() -> None:
    harness = SourceSmokeHarness(http_get=_fake_http_get)

    harness.public_source_smoke("src1", "https://example.com/1")
    harness.authorized_source_smoke("src2", "https://example.com/2", credentials=None)
    report = harness.get_smoke_report()

    assert report["total_sources_smoked"] == 2
    assert report["live_verified"] == 1
    assert report["config_required"] == 1
    assert len(report["traces"]) == 2


def test_archive_fallback_attempted_when_direct_fails() -> None:
    harness = SourceSmokeHarness(http_get=_fake_http_get)

    trace = harness.public_source_smoke(
        "test",
        "https://definitely-not-a-real-domain-99999.invalid",
    )

    assert trace.status == SmokeStatus.ARCHIVE_ACCESSED
    assert trace.archive_fallback_used is True
    assert trace.archive_url.startswith("https://web.archive.org/")
    assert trace.trace_id


def test_public_archive_access_produces_session_trace() -> None:
    access = PublicArchiveAccess(fetch_url=_fake_fetch_url, sleeper=_no_sleep)

    session = access.research_subject(
        subject_name="Demo Enterprise",
        target_urls=["https://httpbin.org/get"],
        use_archive_fallback=True,
    )
    trace = session.to_dict()

    assert trace["actions_count"] > 0
    assert "target_subject_hash" in trace
    assert "Demo Enterprise" not in str(trace)
    assert trace["direct_accesses"] == 1


def test_human_behavior_simulation_documented() -> None:
    access = PublicArchiveAccess(fetch_url=_fake_fetch_url, sleeper=_no_sleep)

    assert access.HUMAN_BEHAVIOR["page_load_wait_ms"] == 3000
    assert access.HUMAN_BEHAVIOR["between_pages_wait_ms"] == 5000
    for key, ms in access.HUMAN_BEHAVIOR.items():
        assert 500 <= ms <= 30000, f"{key} outside human range: {ms}ms"


def test_archive_endpoints_configured() -> None:
    eps = PublicArchiveAccess.ARCHIVE_ENDPOINTS

    assert "wayback" in eps
    assert "archive_is" in eps
    assert "google_cache" in eps
