"""Mass cross-platform profiler must be explicit-only by default."""

from __future__ import annotations


def _make_gate():
    from core.user_auth_gate import UserAuthorizationGate

    return UserAuthorizationGate("test")


def test_mass_profiler_blocks_until_authorized() -> None:
    from adapters.mass_profiler import MassCrossPlatformProfiler

    adapter = MassCrossPlatformProfiler(_make_gate())

    assert adapter.massive_cross_check("demo") == {
        "error": "source_not_authorized",
        "source": "mass_cross_platform_profiler",
    }


def test_mass_profiler_authorization_can_be_revoked() -> None:
    from adapters.mass_profiler import MassCrossPlatformProfiler

    gate = _make_gate()
    adapter = MassCrossPlatformProfiler(gate)

    adapter.enable()
    assert adapter.is_available()

    gate.disable_source("mass_cross_platform_profiler")
    assert not adapter.is_available()


def test_mass_profiler_authorized_path_uses_public_profile_checks(monkeypatch) -> None:
    from adapters.mass_profiler import MassCrossPlatformProfiler

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b"<html><title>demo profile</title><body>public profile</body></html>"

    monkeypatch.setattr(
        MassCrossPlatformProfiler,
        "ALL_PLATFORMS",
        {"code": [("ExampleCode", "example.com/{u}", "public code profile")]},
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr("time.sleep", lambda *_args, **_kwargs: None)

    adapter = MassCrossPlatformProfiler(_make_gate())
    adapter.enable()
    result = adapter.massive_cross_check("demo")

    assert result["response_status"] == 200
    assert result["source"] == "mass_cross_platform_verification"
    assert result["fields"]["platforms_found"] == 1
    assert result["fields"]["platforms_checked"] == 1
    assert result["fields"]["by_category"] == {"code": ["ExampleCode"]}
