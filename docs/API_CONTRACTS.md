# API and Plugin Contracts

This document defines the stable JSON surfaces used by the local API, CLI tools,
Codex adapters, and future portal/plugin builds.

本文档定义本地 API、CLI 工具、Codex 适配版、门户在线体验和后续插件版共同消费的稳定
JSON 契约。

## Positioning / 定位

`wallstreet-tieling` is an Enterprise Intelligence & Risk Discovery System. Its
interfaces should favor evidence, provenance, graph relationships, and monitoring
signals over long unstructured reports.

`wallstreet-tieling` 是企业情报与风险发现系统。接口优先输出证据、来源、图谱关系和监控信号，
而不是只输出一篇很长的总结报告。

## `GET /api/agent-tools`

Returns the machine-readable desktop-agent adapter manifest shared by REST,
CLI, MCP, Codex, Claude Code, Hermes, Doubao Office Task Mode, OpenClaude-style
agents, and WorkBuddy.

Response:

```json
{
  "data": {
    "type": "agent_tool_adapter_manifest",
    "release_target": "desktop_agent_alpha",
    "host_ids": ["codex", "claude_code", "hermes"],
    "shared_tools": [
      {
        "name": "release_readiness",
        "required_output_fields": [
          "delivery_decision.status",
          "delivery_decision.remaining_variant_blocker_count",
          "delivery_decision.variant_next_gate_count",
          "delivery_closure.status",
          "delivery_closure.required_preserved_fields",
          "delivery_closure.required_verification_commands",
          "release_preflight.package_candidate_ready"
        ]
      },
      {
        "name": "release_preflight",
        "required_output_fields": [
          "package_candidate_ready",
          "final_submission_ready",
          "final_submission_blockers",
          "packaging_review.dry_run_command",
          "agent_handoff.safe_claim"
        ]
      },
      {
        "name": "delivery_audit",
        "required_output_fields": [
          "status",
          "ready_for_local_packaging",
          "failed_checks",
          "coverage",
          "verification_evidence.latest_acceptance",
          "safe_claim"
        ]
      },
      {
        "name": "objective_audit",
        "required_output_fields": [
          "status",
          "completion_percent",
          "requirements",
          "failed_requirements",
          "release_gate.delivery_audit_status"
        ]
      },
      {
        "name": "development_requirements",
        "required_output_fields": [
          "delivery_decision.status",
          "delivery_decision.full_product_status"
        ]
      },
      {
        "name": "investigate_company",
        "required_output_fields": [
          "report_exports.directory_bundle.agent_handoff",
          "report_exports.directory_bundle.agent_handoff.relationship_resolution",
          "report_exports.directory_bundle.agent_handoff.source_strengthening",
          "qyyjt_public_origin_handoff.agent_autorun",
          "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun",
          "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun",
          "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun",
          "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun",
          "report_exports.directory_bundle.agent_handoff.report_artifact_autorun",
          "report_exports.directory_bundle.agent_handoff.delivery_decision"
        ]
      }
    ],
    "execution_matrix": [
      {
        "phase": "release_gate",
        "tool": "release_readiness",
        "done_condition": "delivery_decision.status is desktop_agent_alpha_release_candidate and runtime_delivery.release_blocking_surface_count is 0"
      },
      {
        "phase": "delivery_audit",
        "tool": "delivery_audit",
        "done_condition": "status is pass, ready_for_local_packaging is true, and failed_checks is empty"
      },
      {
        "phase": "investigation_run",
        "tool": "investigate_company",
        "done_condition": "packet type is investigation_packet with one_click_readiness and directory_bundle.agent_handoff"
      }
    ],
    "first_run_recipe": {
      "sequence": [
        "release_readiness",
        "delivery_audit",
        "connector_catalog",
        "development_requirements",
        "agent_tool_adapters",
        "investigate_company"
      ],
      "preserve_before_summarizing": [
        "quality_gate",
        "evidence_ledger",
        "connector_catalog.source_strengthening_queue",
        "connector_catalog.source_strengthening_queue[].implementation_pack",
        "connector_catalog.source_strengthening_queue[].execution_plan",
        "connector_catalog.qyyjt_benchmark.summary.public_origin_execution_summary",
        "one_click_readiness",
        "qyyjt_public_origin_handoff",
        "qyyjt_public_origin_handoff.agent_autorun",
        "report_exports.premium_html",
        "report_exports.portable_html.premium_profile",
        "report_exports.directory_bundle.agent_handoff",
        "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
        "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun",
        "report_exports.directory_bundle.agent_handoff.report_artifact_autorun",
        "report_exports.directory_bundle.agent_handoff.source_strengthening"
      ]
    },
    "default_host_id": "codex",
    "primary_host_id": "codex",
    "secondary_host_ids": ["workbuddy_expert_team"],
    "host_priority_order": ["codex", "universal"],
    "adapter_lookup": {
      "codex": {
        "primary_mode": "codex_plugin_mcp",
        "delivery_priority": {
          "lane": "primary",
          "rank": 1
        },
        "fallback_order": ["Codex plugin", "MCP", "CLI", "skill prompt"],
        "smoke_command": "npm run codex:mcp-smoke",
        "execution_matrix_ref": "agent_tool_adapter_manifest.execution_matrix",
        "required_packet_field_count": 9
      }
    },
    "adapters": [
      {
        "host_id": "codex",
        "tool_sequence": [
          "release_readiness",
          "delivery_audit",
          "connector_catalog",
          "development_requirements",
          "agent_tool_adapters",
          "investigate_company"
        ],
        "fallback_order": ["Codex plugin", "MCP", "CLI", "skill prompt"],
        "required_packet_fields": [
          "report_exports.agent_decision_digest",
          "enterprise_cognition.relationship_resolution_v1",
          "enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue",
          "report_exports.premium_html",
          "report_exports.portable_html.premium_profile",
          "report_exports.directory_bundle",
          "report_exports.directory_bundle.agent_handoff",
          "report_exports.directory_bundle.agent_handoff.report_visibility.premium_html",
          "report_exports.directory_bundle.agent_handoff.source_health.source_resilience.agent_autorun",
          "report_exports.directory_bundle.agent_handoff.capital_risk_panel.agent_autorun",
          "report_exports.directory_bundle.agent_handoff.relationship_graph_audit.agent_autorun",
          "report_exports.directory_bundle.agent_handoff.relationship_resolution.agent_autorun",
          "report_exports.directory_bundle.agent_handoff.report_artifact_autorun",
          "report_exports.directory_bundle.agent_handoff.source_strengthening",
          "report_exports.directory_bundle.agent_handoff.delivery_decision"
        ],
        "smoke_command": "npm run codex:mcp-smoke"
      }
    ],
    "required_smoke_commands": ["npm run agent:host-smoke"]
  }
}
```

Rules:

- Agents should call this before host-specific formatting so they preserve the
  required packet fields.
- Agents must preserve `delivery_decision`,
  `enterprise_cognition.relationship_resolution_v1.resolution_summary.verification_queue`,
  `report_exports.directory_bundle.agent_handoff.relationship_resolution`,
  `report_exports.directory_bundle.agent_handoff.delivery_decision`, and
  `report_exports.directory_bundle.agent_handoff.source_strengthening` instead
  of converting those machine-readable release fields into prose only.
- The adapter manifest is current-release scope for desktop-agent alpha.
- Polished immersive HTML, mobile apps, mini-programs, and standalone desktop
  apps remain later-version surfaces.

## `GET /api/release-preflight`

Returns the desktop-agent alpha local packaging go/no-go preflight. This is the
smallest endpoint for agents that need to decide whether the current package can
enter local alpha packaging review without parsing the full release payload.

Response highlights:

```json
{
  "data": {
    "type": "desktop_agent_alpha_release_preflight",
    "target": "desktop_agent_alpha",
    "status": "ready_for_local_packaging",
    "package_candidate_ready": true,
    "final_submission_ready": false,
    "final_submission_blockers": [
      "capture marketplace/operator screenshots after final acceptance"
    ],
    "packaging_review": {
      "dry_run_command": "npm pack --dry-run --json",
      "delivery_audit_command": "npm run delivery:audit"
    },
    "agent_handoff": {
      "safe_claim": "Desktop-agent alpha release candidate, not final polished product launch readiness."
    }
  }
}
```

Rules:

- `package_candidate_ready=true` means local desktop-agent alpha package gates
  are satisfied by the current release contract and acceptance evidence.
- `final_submission_ready=false` means screenshots, clean branch publication,
  or external marketplace/operator review artifacts are still separate tasks.
- Agents must not convert this into a final product launch claim.

## `GET /api/delivery-audit`

Returns the single desktop-agent alpha go/no-go audit. Agents should call this
after `release_readiness` and before spending work on host-specific formatting.

Response highlights:

```json
{
  "data": {
    "type": "desktop_agent_alpha_delivery_audit",
    "target": "desktop_agent_alpha",
    "status": "pass",
    "ready_for_local_packaging": true,
    "final_submission_ready": false,
    "failed_checks": [],
    "coverage": {
      "source_resilience": {"covered": true},
      "qyyjt_public_origin": {"covered": true},
      "relationship_graph": {"covered": true},
      "capital_risk": {"covered": true},
      "report_visibility": {"covered": true}
    },
    "safe_claim": "Desktop-agent alpha release candidate, not final polished product launch readiness."
  }
}
```

Rules:

- `status=pass` is the concise local package go/no-go result for desktop-agent
  alpha only.
- `failed_checks` and `blocking_items` are the next task list if the audit is
  blocked.
- This endpoint does not certify external marketplace approval or final
  product launch readiness.

## `GET /api/objective-audit`

Returns the active development objective audit. Use it before marking a release
objective complete because it maps the objective to concrete evidence and
remaining work.

Response highlights:

```json
{
  "data": {
    "type": "objective_completion_audit",
    "status": "in_progress",
    "completion_percent": 90,
    "release_gate": {
      "delivery_audit_status": "pass",
      "ready_for_local_packaging": true
    },
    "failed_requirements": []
  }
}
```

Rules:

- `failed_requirements` is the authoritative next task list for the active
  objective.
- Do not mark the goal complete while this list is non-empty.

## `POST /api/aggregate`

Follow-up subject expansion endpoint for desktop agents. Use it only after an
investigation packet identifies a related company, controller, address cluster,
or other subject that needs bounded association expansion.

Request:

```json
{
  "subject_id": "company:demo-related",
  "subject_name": "Demo Related Co.",
  "max_depth": 1
}
```

Response contract:

```json
{
  "subject": {
    "id": "company:demo-related",
    "name": "Demo Related Co.",
    "identity": {}
  },
  "relationship_graph": {},
  "profile": {
    "identity": {},
    "contacts": {},
    "addresses": {},
    "related_entities": [],
    "social_relations": {}
  },
  "adapter_summary": {
    "total_sources": 6,
    "failed": [],
    "empty": [],
    "cache_hits": 0
  }
}
```

Equivalent CLI:

```bash
npx wallstreet-tieling --aggregate-subject "company:demo-related" --subject-name "Demo Related Co." --max-depth 1
```

Rules:

- `subject_id` is required.
- `max_depth` is clamped to `1..5`.
- `subject`, `relationship_graph`, and `profile` are stable Agent-facing
  aliases. Legacy fields such as `identity`, `relation_graph`, and
  `related_entities` may still be present for compatibility.
- Empty aggregation output is a coverage gap, not a clean relationship finding.

## `GET /api/requirements`

Returns the executable development priority board used by desktop agents to
decide whether the current package is ready for desktop-agent alpha handoff or
still blocked for full-product launch.

Response highlights:

```json
{
  "data": {
    "type": "development_requirements_board",
    "completion_percent": 94,
    "delivery_decision": {
      "type": "development_delivery_decision",
      "current_target": "desktop_agent_alpha",
      "status": "desktop_agent_alpha_release_candidate",
      "desktop_agent_release_candidate": true,
      "full_product_status": "not_final_release_ready"
    },
    "summary": {
      "desktop_agent_delivery": "desktop_agent_alpha_release_candidate",
      "release_decision": "not_final_release_ready"
    }
  }
}
```

Rules:

- `delivery_decision.status` is the field desktop agents should use for current
  package handoff decisions.
- `full_product_status` remains separate because premium HTML, hosted
  operations, and later output forms are not current-release blockers for the
  desktop-agent alpha.

## `POST /api/risk-graph`

Request:

```json
{
  "company": "Demo Graph Co., Ltd.",
  "config": "optional/path/to/datasources.yaml",
  "offline_fixture": false,
  "retrieval_concurrency": 4,
  "fanout_rounds": 1,
  "max_fanout_tasks": 24,
  "store": "optional/path/to/risk-events.jsonl"
}
```

Rules:

- `company` or `name` is required.
- `config` and `offline_fixture` are mutually exclusive.
- `retrieval_concurrency` is clamped to `1..20`.
- `fanout_rounds` is clamped to `0..3`; the default is one bounded expansion
  round after seed retrieval.
- `max_fanout_tasks` is clamped to `0..80`; the default is `24`.
- If `config` is provided, configured datasource health/routing diagnostics are
  included in the response.

规则：

- 必须提供 `company` 或 `name`。
- `config` 与 `offline_fixture` 不能同时使用。
- `retrieval_concurrency` 会被限制在 `1..20`。
- 提供 `config` 时，响应会包含数据源健康状态与路由诊断。

Response:

```json
{
  "data": {
    "company": "Demo Graph Co., Ltd.",
    "summary": {
      "entity_count": 3,
      "relation_count": 2,
      "evidence_count": 1,
      "risk_event_count": 1,
      "highest_severity": "high",
      "queried_sources": ["offline_court_fixture"],
      "failed_sources": [],
      "alert_count": 1
    },
    "nodes": [],
    "edges": [],
    "evidence": [],
    "risk_events": [],
    "timeline": [],
    "diagnostics": {
      "record_quality": {
        "report_count": 1,
        "ok_count": 1,
        "finding_count": 0,
        "finding_codes": {}
      },
      "source_routing": {
        "configured_count": 2,
        "available_count": 1,
        "health_reports": {
          "public_api": {
            "source_name": "public_api",
            "source_type": "rest_api",
            "ok": true,
            "status": "up",
            "endpoint": "https://example.invalid/public_api",
            "latency_ms": 42.15
          }
        }
      },
      "monitoring_delta": {
        "new_event_count": 1,
        "recurring_event_count": 0,
        "not_seen_in_current_scan_count": 0
      }
    }
  }
}
```

### Nodes / 节点

Nodes represent entities found from public or authorized evidence:

- `company`
- `person`
- `address`
- `phone`
- `email`
- `domain`
- `account`
- `asset`
- `case`
- `project`

节点表示从公开或授权证据中抽取出的实体，包括企业、人、地址、联系方式、域名、公开账号、
资产、案件和项目等。

### Edges / 关系

Edges are evidence-backed relations. Common relation types include:

- `mentioned_with`
- `public_role_or_control_lead`
- `public_address_lead`
- `public_contact_lead`
- `public_web_footprint`
- `public_case_lead`
- `public_project_lead`
- `public_asset_lead`
- `has_risk_event`

每条关系都必须带 `evidence_ids`，方便上层 UI 或插件回溯来源。

### Evidence / 证据

Evidence rows preserve:

- source name and source profile
- title and URL
- observed time
- confidence
- claims
- source legitimacy metadata

证据行必须保留来源、URL、观察时间、置信度、原始 claim 和来源合法性元数据。

### Monitoring Delta / 监控变化

### Record Quality / 记录质量

`diagnostics.record_quality` summarizes the standardized-record quality reports
returned by data-source tools:

- `report_count`: number of connector quality reports included in this run.
- `ok_count`: reports without blocking record-quality errors.
- `finding_count`: total warnings/errors reported by connectors.
- `finding_codes`: grouped finding codes for UI badges and connector readiness.

`diagnostics.record_quality` 汇总本次检索中数据源工具返回的标准化记录质量报告：

- `report_count`：本次包含的连接器质量报告数量。
- `ok_count`：没有阻断性质量错误的报告数量。
- `finding_count`：连接器返回的警告/错误总数。
- `finding_codes`：按 code 分组的质量问题，便于 UI 标记和连接器就绪度判断。

### Source Routing Health / 数据源路由健康

`diagnostics.source_routing.health_reports` exposes structured datasource
connectivity reports for plugin and portal status panels:

- `ok`: whether the source is currently routable.
- `status`: `up`, `down`, `skipped`, `challenge`, or `error`.
- `endpoint`: the checked endpoint without embedded credentials.
- `latency_ms`: check latency for observability.
- `auth_challenge`: structured challenge handoff metadata when authorization or
  human verification is required.

`diagnostics.source_routing.health_reports` 为插件和门户状态面板提供结构化数据源健康报告：

- `ok`：当前是否可路由。
- `status`：`up`、`down`、`skipped`、`challenge` 或 `error`。
- `endpoint`：本次检查的端点，不包含账号密码。
- `latency_ms`：连通性检测耗时。
- `auth_challenge`：需要授权或人机校验时的结构化交接信息。

`diagnostics.monitoring_delta` compares the current scan against the historical
JSONL event ledger:

- `new_event_count`: newly discovered risk events.
- `recurring_event_count`: previously seen events reproduced in this scan.
- `not_seen_in_current_scan_count`: historical events not reproduced in this scan.

Important: `not_seen_in_current_scan` is not proof that a risk is resolved. It
only means this run did not reproduce the same event.

`diagnostics.monitoring_delta` 用于说明本次扫描相对历史账本的变化：

- `new_event_count`：新增风险事件。
- `recurring_event_count`：本次仍然复现的历史风险事件。
- `not_seen_in_current_scan_count`：历史存在但本次未复现的风险事件。

注意：本次未复现不等于风险已经解除，只表示这一轮没有再次发现同一事件。

## CLI Contracts / CLI 契约

Investigation packet export fields:

```json
{
  "type": "investigation_packet",
  "report_markdown": "# ...",
  "one_click_readiness": {
    "type": "one_click_readiness",
    "status": "usable_with_operator_followup",
    "coverage_gap_count": 2,
    "coverage_gap_severity": "medium",
    "coverage_attempt_ratio": 0.8,
    "coverage_next_action": "Complete missing-domain recovery and inspect no-evidence sources before relying on final risk conclusions.",
    "source_resilience_recommended_step": {
      "type": "operator_recovery_step",
      "title": "Retry no-evidence or challenged sources with configured credentials",
      "status": "ready_to_run",
      "retry_policy": {
        "type": "coverage_recovery_retry_policy",
        "retryable": true,
        "max_attempts": 3,
        "backoff": "exponential_jitter",
        "timeout_seconds": 45,
        "concurrency": 1
      }
    },
    "source_resilience_retry_policy": {
      "type": "coverage_recovery_retry_policy",
      "retryable": true,
      "requires_user_authorization": false,
      "max_attempts": 3,
      "safe_fallback_rule": "Use public or user-authorized fallback sources only"
    },
    "source_resilience_retryable": true,
    "source_resilience_retry_max_attempts": 3,
    "source_resilience_recommended_step_ready_to_run": true,
    "source_recovery_replay_route": {
      "type": "source_recovery_replay_route",
      "tool": "investigate_company",
      "command": "npx wallstreet-tieling --investigate \"Demo Graph Co., Ltd.\" --report-only",
      "retry_limit": 3,
      "done_condition": "source_replay_records_admissible_evidence_or_explicit_empty_or_blocked_result_with_url_time_status",
      "non_reliance_caveat": "Until recovery is replayed or explicitly recorded as empty/blocked, do not treat missing coverage as a low-risk conclusion or company fact."
    },
    "capital_verification_queue_count": 2,
    "capital_verification_queue": [
      {
        "step_id": "CAP-VERIFY-001",
        "priority": "P0",
        "kind": "capital_row_verification",
        "target_title": "Verify capital pressure row",
        "done_condition": "confirm source provenance and admitted capital fact"
      }
    ],
    "capital_verification_top_step": {
      "type": "capital_verification_step",
      "title": "Verify shareholder and capital movement evidence"
    },
    "relationship_graph_audit_queue_count": 3,
    "relationship_graph_audit_queue": [
      {
        "step_id": "REL-AUDIT-001",
        "priority": "P0",
        "kind": "missing_evidence_relationship_edge",
        "target": "Subject Co -> Related Co",
        "evidence_ids": [],
        "done_condition": "attach_evidence_ids_or_remove_edge_from_fact_graph"
      }
    ],
    "relationship_graph_audit_top_step": {
      "type": "relationship_graph_audit_step",
      "title": "Review evidence-backed relationship edges"
    },
    "acceptance_closure_summary": {
      "type": "acceptance_closure_summary",
      "status": "needs_operator_followup",
      "blocking_count": 3,
      "open_domains": ["source_recovery", "coverage", "relationship_audit"],
      "next_action": "Run the first ranked operator work item before final reliance"
    }
  },
  "qyyjt_public_origin_handoff": {
    "type": "qyyjt_public_origin_handoff",
    "status": "operator_required",
    "execution_queue_count": 4,
    "top_step": {
      "type": "qyyjt_public_origin_step",
      "title": "Run public-origin lookup for QYYJT-style fields"
    },
    "section_work_orders": [
      {
        "work_order_id": "QYYJT-SECTION-01",
        "report_section": "subject_resolution",
        "priority": "P0",
        "query_families": ["company + registration/basic profile"],
        "required_fields": ["legal_name", "identifier", "entity_type"],
        "admission_policy": "Public-origin rows stay lead-only until provenance, required fields, and entity-match gates pass"
      }
    ]
  },
  "report_exports": {
    "type": "report_exports",
    "current_release": "desktop_agent_packet_exports",
    "formats": ["markdown", "json_packet", "portable_html", "print_package", "directory_bundle"],
    "markdown": {
      "filename": "subject-due-diligence-report.md",
      "mime_type": "text/markdown; charset=utf-8",
      "content_field": "report_markdown"
    },
    "portable_html": {
      "filename": "subject-due-diligence-report.html",
      "mime_type": "text/html; charset=utf-8",
      "document": "<!doctype html>...",
      "content_policy": "contains the full Markdown report in a printable escaped preformatted block; no findings are dropped",
      "first_screen_handoff_cards": [
        "capital verification steps",
        "relationship audit steps"
      ]
    },
    "json_packet": {
      "filename": "subject-investigation-packet.json",
      "content_field": "entire investigation_packet"
    },
    "directory_bundle": {
      "runtime_entrypoint": "bin/investigate.py --export-dir",
      "integrity_verifier_entrypoint": "bin/verify_report_bundle.py <export-dir>",
      "verifier_output_fields": [
        "ok",
        "agent_handoff.checked",
        "agent_handoff.schema_valid",
        "agent_handoff.decision_digest_present",
        "agent_handoff.delivery_checklist_present",
        "agent_handoff.bundle_integrity_present",
        "agent_handoff.bundle_verification_present",
        "agent_handoff.bundle_verification_ready_to_run",
        "agent_handoff.bundle_ready_to_verify",
        "agent_handoff.report_visibility_present",
        "agent_handoff.capital_risk_panel_present",
        "agent_handoff.source_strengthening_present",
        "agent_handoff.source_strengthening_runtime_companion_present",
        "agent_handoff.acceptance_closure_present",
        "agent_handoff.qyyjt_public_origin_present",
        "agent_handoff.source_resilience_present",
        "agent_handoff.relationship_graph_audit_present"
      ],
      "verification_recipe": {
        "type": "report_bundle_verification_recipe",
        "command": "python bin/verify_report_bundle.py <export-dir>",
        "expected_exit_code": 0,
        "success_condition": "ok=true and agent_handoff.schema_valid=true and agent_handoff.bundle_ready_to_verify=true",
        "required_output_fields": [
          "ok",
          "checked_count",
          "agent_handoff.checked",
          "agent_handoff.schema_valid",
          "agent_handoff.delivery_checklist_present",
          "agent_handoff.bundle_integrity_present",
          "agent_handoff.bundle_verification_present",
          "agent_handoff.bundle_verification_ready_to_run",
          "agent_handoff.bundle_ready_to_verify",
          "agent_handoff.report_visibility_present",
          "agent_handoff.premium_html_report_visibility_present",
          "agent_handoff.capital_risk_panel_present",
          "agent_handoff.source_strengthening_present",
          "agent_handoff.source_strengthening_runtime_companion_present",
          "agent_handoff.acceptance_closure_present",
          "agent_handoff.qyyjt_public_origin_present",
          "agent_handoff.source_resilience_present",
          "agent_handoff.relationship_graph_audit_present"
        ]
      },
      "manifest_filename": "report-export-manifest.json",
      "agent_handoff": {
        "filename": "agent-handoff.json",
        "schema_fields": [
          "delivery_decision",
          "delivery_files",
          "bundle_integrity",
          "bundle_verification",
          "delivery_checklist",
          "report_visibility",
          "capital_risk_panel",
          "trust_boundaries",
          "decision_digest",
          "next_actions",
          "acceptance_closure"
        ],
        "content": "delivery files, acceptance closure, operator work, closure steps, control path verification queue, source-health, source recovery execution queue, source resilience retry policy, graph capital exposure, relationship graph audit summary, qyyjt public-origin section work orders, bundle verification, report visibility, capital risk panel, reliance limitations, and print handoff cards"
      }
    },
    "print_package": {
      "operational_handoff": {
        "cards": [
          {
            "id": "acceptance_closure_summary",
            "status": "needs_operator_followup",
            "done_condition": "operator_work_queue_empty_or_each_open_item_has_explicit_non_reliance_caveat"
          }
        ]
      },
      "docx": {
        "renderer_status": "runtime_cli_renderer_available",
        "renderer_capabilities": [
          "section_inventory_toc",
          "page_footer_field",
          "chart_manifest_data_rows",
          "image_evidence_inventory_items",
          "embedded_local_image_evidence",
          "operational_handoff_tables",
          "native_word_tables"
        ]
      }
    },
    "future_formats": {
      "docx_red_head": "runtime_cli_renderer_available_via_export_docx",
      "immersive_premium_html": "p2_visual_polish_not_current_release_blocker"
    }
  }
}
```

Desktop-agent hosts should use `report_exports.markdown.content_field` for the
printable Markdown body, `report_exports.portable_html.document` for a portable
HTML file, and the full JSON packet for evidence/audit replay. Portable HTML
also exposes first-screen handoff cards so desktop agents can immediately show
capital verification and relationship audit follow-up work without truncating
the report body. `agent-handoff.json.report_visibility` summarizes the portable
HTML filename, full-body preservation flag, image evidence inventory, source
provenance appendix counts, section inventory count, chart manifest count, and
recommended open order for low-context hosts.
`agent-handoff.json.capital_risk_panel` gives low-context hosts a compact,
evidence-bounded capital/relationship risk status with queue counts, edge
counts, reliance gating, and the next verification action. Hosts must not
promote a clean capital-risk conclusion when this panel reports blocked,
unknown, or verification-required status.
`bin/verify_report_bundle.py <export-dir>` validates the file manifest and also
fails when `report-export-manifest.json.agent_summary` drifts from
`agent-handoff.json` for `delivery_decision`, `decision_digest`,
`delivery_status`, or `acceptance_closure_status`.

Red-head Word output is available through the runtime CLI renderer:

```bash
python bin/investigate.py "Demo Graph Co., Ltd." --offline-fixture --export-docx out/demo.docx
python bin/investigate.py "Demo Graph Co., Ltd." --offline-fixture --export-html out/demo.html --export-markdown out/demo.md --export-json out/demo.json
python bin/investigate.py "Demo Graph Co., Ltd." --offline-fixture --export-dir out/demo-report-bundle
npx wallstreet-tieling --investigate "Demo Graph Co., Ltd." --offline-fixture --export-docx out/demo.docx --export-html out/demo.html
```

The DOCX package advertises official document metadata, red-head separator
rules, chart data rows, native chart summary panels, image evidence inventory
items, local/data-uri embedded image evidence, operational handoff tables, and
native Word tables through `report_exports.print_package.docx.renderer_capabilities`.
Remote image URLs are preserved as evidence inventory rows without network fetches.
The portable HTML is still a dependency-free desktop-agent report artifact, but
it now surfaces the same report evidence as visible first-screen panels:
`Visual evidence panels`, `Source provenance appendix`, `Relationship and
capital appendix`, delivery checklist, agent decision digest, image evidence
summary, and the full escaped Markdown body.
Premium immersive HTML remains a later visual-polish target,
not current-release blocking gates.

Directory bundle exports write `agent-handoff.json.delivery_decision` and mirror
it into `report-export-manifest.json.agent_summary.delivery_decision`. Desktop
agents should use that field to distinguish a normal
`desktop_agent_alpha_release_candidate` bundle from a Node fallback bundle that
preserves files but still needs Python runtime restoration before final handoff.
`bin/verify_report_bundle.py <export-dir>` also rejects stale bounded
`agent_summary` previews when `bundle_verification`, `report_visibility`,
`capital_risk_panel`, source resilience, work-queue counts, public-origin top
work, capital top step, relationship top step, or top next actions drift from
`agent-handoff.json`.

Desktop-agent hosts should also read `one_click_readiness.coverage_gap_count`,
`coverage_gap_severity`, `coverage_attempt_ratio`, `coverage_next_action`,
`source_resilience_recommended_step`, `source_resilience_retry_policy`,
`source_resilience_retryable`, `source_resilience_retry_max_attempts`,
`monitoring_seed.recovery_execution_queue.queue[].replay_route`,
`monitoring_seed.recovery_execution_queue.blocked_preview[].replay_route`, `capital_relationship_status`,
`capital_verification_queue_count`,
`relationship_graph_audit_queue_count`, and
`acceptance_closure_summary` before treating a packet as final.
`qyyjt_public_origin_handoff` carries the public-origin queue and per-report-section
work orders for QYYJT-style field recovery. `not_searched` means coverage was not attempted; `no_evidence`
means attempted sources returned no usable evidence.

`GET /api/connectors` also returns `source_strengthening_queue`, a ranked list
of connector work orders for Codex/mainline source hardening. Each row includes
`priority`, `lane`, `connector`, `missing_contracts`, `next_action`,
`implementation_pack`, `runtime_companion`, `acceptance_commands`,
`done_condition`, and `do_not`.
The same payload exposes advanced default-off sources through
`groups.explicit_only` and `connectors[].data_effectiveness`. Current advanced
China domestic entries include `enterprise_tax_credit_public_records`,
`enterprise_judicial_asset_public_records`,
`enterprise_mofcom_overseas_investment_public_records`,
`enterprise_baidu_aiqicha_public_aggregation`, and
`enterprise_shuidi_credit_public_aggregation`. Desktop agents must preserve
these rows when the user asks for deeper authorized coverage, but must not
enable them implicitly or promote their rows into report facts before
authorization, provenance, entity-match, and admission gates pass.
The queue may be empty after all connector contracts are strengthened; in that
state `summary.source_strengthening.candidate_count` must be `0`, `top_connectors`
and `by_priority` must be empty, and investigation/export agent handoffs should
use `source_strengthening.status == complete` rather than fabricating follow-up
work orders.
`implementation_pack` points the desktop agent at target files, source-specific
field contracts, and focused tests. The official China registry, credit-publicity,
and court-enforcement catalog rows expose validated snapshot/manual-gate parsing
as lead-capable source strengthening work while remaining default-off and
non-fact-capable until entity-match and report-admission gates pass.
OpenSanctions and IDB public dataset catalog work orders expose dedicated
dataset-selection, refresh, local-index, license, and subject-match contracts;
catalog metadata is coverage evidence only and cannot become a subject risk fact
without a reviewed local/API subject record plus exact/strong entity matching.
GLEIF relationship traversal is exposed as
`gleif_lei_relationship_traversal_public_api`, a default-off production-ready
relationship source for parent/branch relationship endpoints. It reuses the
stable `gleif_lei_public_api` identity lookup and emits standardized
`gleif_relationship_edge` records with subject/related LEI fields, relationship
type/status, source URL, evidence rows, graph entities, and structured
`entity_match` gates. The source is no longer listed in
`source_strengthening_queue`; report-fact reliance still requires exact/strong
entity matching, relationship period/status review, and admission checks.
For catalog-style risk/enforcement rows, `runtime_companion` and
`execution_plan.runtime_companion` point agents at the configured local subject
index (`opensanctions_local_subject_index` or `idb_local_subject_index`) that
can produce standardized subject-match records after provenance and admission
checks pass.
This queue is
planning metadata only: pending or catalog-only connectors must not be promoted
into report facts until health, standardized-record, provenance, entity-match,
and admission tests pass.

Graph export:

```bash
python bin/risk_graph.py "Demo Graph Co., Ltd." --offline-fixture
```

Monitoring pass:

```bash
python bin/risk_monitor.py "Demo A Co., Ltd." "Demo B Co., Ltd." --offline-fixture
```

Both commands print UTF-8 JSON to stdout and are safe to use in automation.

两个命令都会向 stdout 输出 UTF-8 JSON，可被自动化脚本、Codex 插件或门户在线体验直接消费。
