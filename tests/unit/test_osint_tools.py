#!/usr/bin/env python3
"""Optional SOCMINT tool integration: detection, parsing, runs, recursion, records."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from adapters.osint_tools import (
    AVAILABLE,
    CLAIMED,
    ILLEGAL,
    OPTIONAL_TOOLS,
    UNKNOWN,
    OptionalToolRunner,
    RecursiveIdentitySearch,
    detect_optional_tools,
    extract_follow_up_identifiers,
    parse_holehe_rows,
    parse_maigret_report,
    parse_phoneinfoga_result,
    parse_sherlock_csv,
    tool_run_to_standardized_records,
)
from core.record_quality import audit_standardized_records

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "osint"


def _detection(*installed: str) -> dict:
    return detect_optional_tools(
        which=lambda exe: f"/opt/bin/{exe}" if any(OPTIONAL_TOOLS[t].executable == exe for t in installed) else None,
        find_spec=lambda mod: object() if any(OPTIONAL_TOOLS[t].python_module == mod for t in installed) else None,
        version_of=lambda dist: {"maigret": "0.6.6", "sherlock-project": "0.16.2", "holehe": "1.61"}.get(dist, ""),
    )


class FakeProc:
    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.returncode, self.stderr, self.stdout = returncode, stderr, ""


class FakeRunner:
    """Simulates the CLIs by writing the fixture reports where the real tools would."""

    def __init__(self, fail: set[str] | None = None, timeout: set[str] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail or set()
        self.timeout = timeout or set()

    def __call__(self, cmd, cwd, capture_output, text, timeout, check):
        self.calls.append(cmd)
        tool = os.path.basename(cmd[0])
        if tool in self.timeout:
            raise subprocess.TimeoutExpired(cmd, timeout)
        if tool in self.fail:
            return FakeProc(1, "boom")
        username = cmd[1]
        if tool == "maigret":
            if username == "demo_exec_2026":
                Path(cwd, f"report_{username}_simple.json").write_text((FIX / "maigret_simple_report.json").read_text())
            else:
                Path(cwd, f"report_{username}_simple.json").write_text("{}")
        elif tool == "sherlock":
            Path(cwd, f"{username}.csv").write_text((FIX / "sherlock_print_all.csv").read_text().replace("demo-exec", username))
        elif tool == "holehe":
            Path(cwd, f"holehe_1700000000_{username}_results.csv").write_text((FIX / "holehe_results.csv").read_text())
            return FakeProc(1, "")  # holehe calls exit(msg) after export
        return FakeProc(0)


def test_detection_is_runtime_and_honest() -> None:
    nothing = _detection()
    assert nothing["installed_count"] == 0
    assert all(row["status"] == "not_installed" for row in nothing["tools"].values())
    some = _detection("maigret", "holehe")
    assert some["tools"]["maigret"]["installed"] is True
    assert some["tools"]["maigret"]["version"] == "0.6.6"
    assert some["tools"]["sherlock"]["installed"] is False
    assert some["method"].startswith("runtime")


def test_registry_declares_license_boundaries() -> None:
    for name, spec in OPTIONAL_TOOLS.items():
        assert spec.not_found_semantics, name
        if spec.copyleft:
            assert spec.boundary in {"subprocess", "http_service"}, name  # never imported
    assert OPTIONAL_TOOLS["maigret"].license == "MIT"
    assert OPTIONAL_TOOLS["ghunt"].license == "AGPL-3.0"
    assert "NOT on PyPI" in OPTIONAL_TOOLS["phoneinfoga"].install_hint


def test_parse_maigret_report_keeps_ids_and_similarity() -> None:
    obs = parse_maigret_report((FIX / "maigret_simple_report.json").read_text())
    by_site = {o.site: o for o in obs}
    assert set(by_site) == {"GitHub", "Keybase", "SomeForum"}
    gh = by_site["GitHub"]
    assert gh.status == CLAIMED and gh.check_type == "message" and gh.http_status == 200
    assert gh.ids["fullname"] == "Demo Exec" and gh.ids["location"] == "Shanghai"
    assert by_site["SomeForum"].extra["is_similar"] is True
    ndjson = "\n".join(json.dumps({**v, "sitename": k}) for k, v in json.loads((FIX / "maigret_simple_report.json").read_text()).items())
    assert len(parse_maigret_report(ndjson)) == 3


def test_parse_sherlock_four_states() -> None:
    obs = parse_sherlock_csv((FIX / "sherlock_print_all.csv").read_text())
    assert [o.status for o in obs] == [CLAIMED, AVAILABLE, UNKNOWN, ILLEGAL]
    assert obs[0].response_time_s == pytest.approx(0.41)
    assert obs[2].http_status == 429


def test_parse_holehe_rate_limit_is_gap_and_recovery_kept() -> None:
    obs = parse_holehe_rows((FIX / "holehe_results.csv").read_text(), email="demo.exec@example.invalid")
    status = {o.site: o.status for o in obs}
    assert status == {"github": CLAIMED, "twitter": AVAILABLE, "instagram": UNKNOWN, "gravatar": CLAIMED}
    gravatar = next(o for o in obs if o.site == "gravatar")
    assert gravatar.extra["email_recovery"] == "d*****@example.invalid"


def test_parse_phoneinfoga_result_and_error() -> None:
    payload = json.loads((FIX / "phoneinfoga_local.json").read_text())
    ok = parse_phoneinfoga_result("local", payload, number="+12025550123")
    assert ok[0].status == CLAIMED and ok[0].ids["country"] == "US"
    bad = parse_phoneinfoga_result("numverify", {"error": "no api key"}, number="+12025550123")
    assert bad[0].status == UNKNOWN


def test_runner_reports_missing_tools_as_gaps() -> None:
    runner = OptionalToolRunner(runner=FakeRunner(), detection=_detection())
    run = runner.run_maigret("demo_exec_2026")
    assert run.status == "tool_missing" and "pip install maigret" in run.error
    records = tool_run_to_standardized_records(run)
    assert records[0]["record_type"] == "osint_tool_run"
    assert records[0]["evidence_gaps"][0]["reason"] == "tool_missing"
    assert len(records) == 1


def test_maigret_run_builds_scoped_command_and_records(tmp_path) -> None:
    fake = FakeRunner()
    runner = OptionalToolRunner(runner=fake, detection=_detection("maigret"),
                                workdir_factory=lambda: str(Path(__import__("tempfile").mkdtemp(dir=tmp_path))),
                                proxy="http://127.0.0.1:8080")
    run = runner.run_maigret("demo_exec_2026", top_sites=100, timeout=12)
    cmd = fake.calls[0]
    assert cmd[:2] == ["/opt/bin/maigret", "demo_exec_2026"]
    assert "--top-sites" in cmd and cmd[cmd.index("--top-sites") + 1] == "100"
    assert "--all-sites" not in cmd and "--no-recursion" in cmd and "--proxy" in cmd
    assert run.status == "completed" and run.tool_version == "0.6.6"
    records = tool_run_to_standardized_records(run, subject="Demo Exec")
    assert audit_standardized_records(records).ok
    accounts = [r for r in records if r["record_type"] == "social_account_candidate"]
    assert len(accounts) == 3
    gh = next(r for r in accounts if r["title"].startswith("GitHub"))
    assert gh["profile"]["ids"]["company"] == "Demo Technology Co., Ltd."
    assert gh["evidence"][0]["tool"] == "maigret" and gh["evidence"][0]["query"] == "demo_exec_2026"
    similar = next(r for r in accounts if r["title"].startswith("SomeForum"))
    assert similar["confidence"] <= 0.35
    run_rec = records[0]
    assert run_rec["coverage"]["absence_is_not_proof"] is True
    assert run_rec["run"]["site_scope"]["top_sites"] == 100


def test_all_sites_is_explicit_opt_in(tmp_path) -> None:
    fake = FakeRunner()
    runner = OptionalToolRunner(runner=fake, detection=_detection("maigret"))
    runner.run_maigret("demo_exec_2026", all_sites=True, top_sites=None)
    assert "--all-sites" in fake.calls[0]


def test_sherlock_unknown_and_illegal_become_gaps() -> None:
    runner = OptionalToolRunner(runner=FakeRunner(), detection=_detection("sherlock"))
    run = runner.run_sherlock("demo-exec", sites=["GitLab", "HackerNews"])
    assert run.counts()[CLAIMED] == 1
    records = tool_run_to_standardized_records(run)
    reasons = {g["reason"] for g in records[0]["evidence_gaps"]}
    assert reasons == {"site_unknown", "site_illegal"}
    assert records[0]["coverage"]["not_detected_sites"] == ["HackerNews"]


def test_holehe_nonzero_exit_after_export_is_completed() -> None:
    runner = OptionalToolRunner(runner=FakeRunner(), detection=_detection("holehe"))
    run = runner.run_holehe("demo.exec@example.invalid")
    assert run.status == "completed"
    assert run.counts()[CLAIMED] == 2


def test_timeout_and_failure_are_recorded() -> None:
    runner = OptionalToolRunner(runner=FakeRunner(timeout={"maigret"}, fail={"sherlock"}),
                                detection=_detection("maigret", "sherlock"))
    assert runner.run_maigret("x").status == "timeout"
    failed = runner.run_sherlock("x")
    assert failed.status == "failed" and "boom" in failed.error


def test_phoneinfoga_http_service() -> None:
    calls = []

    def post(url, body, timeout):
        calls.append(url)
        if url.endswith("/local/run"):
            return json.loads((FIX / "phoneinfoga_local.json").read_text())
        raise ConnectionError("scanner disabled")

    runner = OptionalToolRunner(detection=_detection(), http_post=post, phoneinfoga_url="http://127.0.0.1:5000/api")
    run = runner.run_phoneinfoga("+12025550123", scanners=("local", "numverify"))
    assert calls[0] == "http://127.0.0.1:5000/api/v2/scanners/local/run"
    assert run.status == "completed" and run.counts()[CLAIMED] == 1 and run.counts()[UNKNOWN] == 1
    records = tool_run_to_standardized_records(run)
    assert any(r["record_type"] == "phone_number_intel" for r in records)


def test_follow_up_identifiers_and_recursive_search() -> None:
    obs = parse_maigret_report((FIX / "maigret_simple_report.json").read_text())
    seeds = extract_follow_up_identifiers(obs)
    assert ("username", "demo-exec") in seeds
    assert ("email", "demo.exec@example.invalid") in seeds

    runner = OptionalToolRunner(runner=FakeRunner(), detection=_detection("maigret", "sherlock", "holehe"))
    result = RecursiveIdentitySearch(runner, max_depth=1, max_identifiers=10).search("username", "demo_exec_2026")
    visited = {v for _, v in result.visited}
    assert {"demo_exec_2026", "demo-exec", "demo.exec@example.invalid"} <= visited
    assert any(e["to"]["value"] == "demo-exec" and e["via_site"] == "GitHub" for e in result.edges)
    assert not result.truncated
    records = result.standardized_records(subject="Demo Exec")
    assert audit_standardized_records(records).ok
    assert any(r["record_type"] == "identity_relationship" for r in records)
    assert {r["run"]["depth"] for r in records if r["record_type"] == "osint_tool_run"} == {0, 1}


def test_recursive_search_respects_budget() -> None:
    runner = OptionalToolRunner(runner=FakeRunner(), detection=_detection("maigret", "holehe"))
    result = RecursiveIdentitySearch(runner, max_depth=3, max_identifiers=1).search("username", "demo_exec_2026")
    assert len(result.visited) == 1 and result.truncated is True


def test_username_verifier_uses_optional_tool_and_maps_records() -> None:
    from adapters.runtime_deep import UsernameCrossPlatformVerifier
    from core.user_auth_gate import UserAuthorizationGate

    adapter = UsernameCrossPlatformVerifier(UserAuthorizationGate("test"))
    adapter.enable()
    detection = _detection("maigret")
    adapter.use_tool_runner(OptionalToolRunner(runner=FakeRunner(), detection=detection), detection)
    raw = adapter.verify_username("demo_exec_2026")
    assert raw["engine"] == "maigret" and raw["fields"]["platforms_found"] == 3
    out = adapter.standardize_result("demo_exec_2026", raw)
    types = [r["record_type"] for r in out["standardized_records"]]
    assert types[0] == "runtime_cross_platform_username_lead"
    assert "osint_tool_run" in types and types.count("social_account_candidate") == 3
    assert out["health"]["runtime_detection"]["maigret"]["installed"] is True


def test_platform_url_builder_handles_hosts() -> None:
    from adapters.runtime_deep import UsernameCrossPlatformVerifier

    assert UsernameCrossPlatformVerifier._platform_url("dev.to", "a b") == "https://dev.to/a%20b"
    assert UsernameCrossPlatformVerifier._platform_url("medium", "x") == "https://medium.com/@x"
    assert UsernameCrossPlatformVerifier._platform_url("github", "x") == "https://github.com/x"


def test_open_source_integration_is_honest_when_missing() -> None:
    from adapters.deep_osint import OpenSourceOSINTIntegration
    from core.user_auth_gate import UserAuthorizationGate

    adapter = OpenSourceOSINTIntegration(UserAuthorizationGate("test"))
    adapter.enable()
    adapter.use_tool_runner(OptionalToolRunner(runner=FakeRunner(), detection=_detection()))
    missing = adapter.query_tool("maigret", "demo_exec_2026")
    assert missing["executed"] is False and missing["error"] == "optional_tool_not_installed"
    assert missing["response_status"] == 0

    adapter.use_tool_runner(OptionalToolRunner(runner=FakeRunner(), detection=_detection("holehe", "ghunt")))
    ran = adapter.query_tool("holehe", "demo.exec@example.invalid")
    assert ran["executed"] is True and ran["run_status"] == "completed"
    assert ran["fields"]["counts"]["claimed"] == 2
    assert audit_standardized_records(ran["standardized_records"]).ok
    ghunt = adapter.query_tool("ghunt", "demo.exec@example.invalid")
    assert ghunt["executed"] is False and ghunt["error"] == "ghunt_requires_operator_login_session"


def test_cli_detect_and_parse(capsys) -> None:
    import importlib.util as iu

    spec = iu.spec_from_file_location("osint_cli", Path(__file__).resolve().parents[2] / "bin" / "osint_tools.py")
    cli = iu.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main(["--detect"]) == 0
    assert json.loads(capsys.readouterr().out)["type"] == "optional_osint_tool_detection"
    assert cli.main(["--parse", "maigret", "--file", str(FIX / "maigret_simple_report.json"), "--query", "demo_exec_2026"]) == 0
    records = json.loads(capsys.readouterr().out)
    assert [r["record_type"] for r in records].count("social_account_candidate") == 3


def test_registry_lists_optional_osint_and_crawler_connectors() -> None:
    from core.connector_registry import ConnectorRegistry

    registry = ConnectorRegistry()
    for name in ("optional_osint_tool_runs", "crawler_xueqiu_market_community", "crawler_public_site_pages"):
        cap = registry.get(name)
        assert cap is not None and cap.default_enabled is False and cap.standardized_records
    assert registry.get("optional_osint_tool_runs").data_effectiveness()["admission_mode"] == "lead_source_with_exact_match_promotion"
