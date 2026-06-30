# Checkpoint 2026-06-18 EOD

## Branch

- Branch: `codex/security-ci-hardening`
- Local state: ahead of `origin/codex/security-ci-hardening` by 3 commits.
- Push status: latest push attempts failed with GitHub HTTPS connection reset / port 443 connectivity failure.

## Commits Completed Today

- `395d920 feat: add default public intel entrypoint`
- `a180734 feat: add deep subject profile graph`
- `fbe414f feat: plan deep profile retrieval dimensions`
- `4349bad feat: execute bounded entity fanout`
- `f786201 feat: expose bounded fanout controls`
- `91f2f4f feat: summarize subject profile in graph export`

Remote already has commits through `fbe414f`. The final three local commits still need a successful push:

- `4349bad feat: execute bounded entity fanout`
- `f786201 feat: expose bounded fanout controls`
- `91f2f4f feat: summarize subject profile in graph export`

## What Changed

- Added `DefaultPublicIntelTool` as the product-facing default public-intelligence entrypoint.
- Promoted default public/no-credential data-source routing for public web, QYYJT public leads, and Telegram public-service delivery.
- Added `core/subject_profile.py` for deep subject profiles from the evidence graph.
- Added dimensions for identity, controller/ownership, public contacts/accounts, location/activity, asset/solvency, behavior risk, consumption/preference leads, relationship network, public statements, and risk events.
- Added high-sensitivity lead labeling with evidence ids, source names, confidence, verification status, sensitivity, and business relevance.
- Added bounded entity fan-out after seed retrieval: discovered people, addresses, and accounts can generate follow-up retrieval tasks.
- Exposed fan-out controls through API and CLI:
  - `fanout_rounds`, clamped to `0..3`
  - `max_fanout_tasks`, clamped to `0..80`
- Added subject-profile summary to graph export for plugin/UI use without expanding the full profile payload.

## Verification

Latest focused regression:

```powershell
python -m pytest tests/unit/test_default_public_intel_tool.py tests/unit/test_intelligence_retrieval.py tests/unit/test_subject_profile.py tests/unit/test_risk_discovery_pipeline.py tests/unit/test_risk_graph_export.py tests/unit/test_api_server.py tests/unit/test_connector_registry.py tests/unit/test_adapter_audit.py -q
```

Result:

- `44 passed`
- Known warnings: existing Pydantic v1 validator deprecation warnings in `adapters/multi_datasource/__init__.py`

## Dirty Worktree Notes

There are unrelated existing dirty/untracked files in the worktree, including `.colab/*`, `README.md`, `adapters/workbuddy.py`, `api/agent_registry.py`, `config/api_endpoints.yaml`, `core/org_memory.py`, `pytest.ini`, and several untracked audit/release/test files.

Do not revert or stage those unless explicitly reviewing that work.

## Next Recommended Work

1. Retry `git push origin codex/security-ci-hardening`.
2. Audit real adapters with record-quality gates and live/provider-specific readiness reports.
3. Connect the deep subject profile to the portal/API UX so a one-company query returns an understandable executive view.
4. Continue M3 engines: finance depth, industry evolution, product replacement risk, and signal-triggered monitoring.
5. Clean public repo/portal copy separately from private/local experimental artifacts.
