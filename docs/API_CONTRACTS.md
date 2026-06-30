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
    "coverage_next_action": "Complete missing-domain recovery and inspect no-evidence sources before relying on final risk conclusions."
  },
  "report_exports": {
    "type": "report_exports",
    "current_release": "desktop_agent_packet_exports",
    "formats": ["markdown", "json_packet", "portable_html"],
    "markdown": {
      "filename": "subject-due-diligence-report.md",
      "mime_type": "text/markdown; charset=utf-8",
      "content_field": "report_markdown"
    },
    "portable_html": {
      "filename": "subject-due-diligence-report.html",
      "mime_type": "text/html; charset=utf-8",
      "document": "<!doctype html>...",
      "content_policy": "contains the full Markdown report in a printable escaped preformatted block; no findings are dropped"
    },
    "json_packet": {
      "filename": "subject-investigation-packet.json",
      "content_field": "entire investigation_packet"
    },
    "future_formats": {
      "docx_red_head": "p2_template_required_not_current_release_blocker",
      "immersive_premium_html": "p2_visual_polish_not_current_release_blocker"
    }
  }
}
```

Desktop-agent hosts should use `report_exports.markdown.content_field` for the
printable Markdown body, `report_exports.portable_html.document` for a portable
HTML file, and the full JSON packet for evidence/audit replay. Red-head Word
and premium immersive HTML are tracked as P2 output targets, not current-release
blocking gates.

Desktop-agent hosts should also read `one_click_readiness.coverage_gap_count`,
`coverage_gap_severity`, `coverage_attempt_ratio`, and `coverage_next_action`
before treating a packet as final. `not_searched` means coverage was not
attempted; `no_evidence` means attempted sources returned no usable evidence.

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
