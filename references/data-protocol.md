# Wallstreet Tieling Data Protocol 0.5.0

This document defines the public connector contract for Wallstreet Tieling.

目标：任何数据源，不管来自 HTTP API、公开网页、官方平台、即时通讯公共服务入口，还是用户授权的商业 API，都必须先映射成统一记录，再进入证据图谱。

## 1. Standardized Record

Connectors should emit a list of records shaped like this:

```json
{
  "source_name": "public_registry_provider",
  "source_type": "official_platform",
  "source_hint": "registry_sources",
  "entity": "Demo Technology Co., Ltd.",
  "title": "Demo Technology public registry profile",
  "summary": "Legal representative, registered address, and controller lead.",
  "url": "https://example.invalid/registry/profile",
  "published_at": "2026-06-20",
  "confidence": 0.86,
  "raw": {
    "legal_representative": "Alice Zhang",
    "actual_controller": {
      "name": "Bob Li"
    },
    "registered_address": "No. 1 Finance Road"
  },
  "evidence": [
    {
      "claim": "Alice Zhang is listed as legal representative."
    }
  ],
  "risk_events": [
    {
      "risk_category": "ownership",
      "severity": "medium",
      "title": "Controller change signal",
      "summary": "Provider reported a controller-change lead.",
      "confidence": 0.7
    }
  ]
}
```

Required fields:

- `source_name`: stable provider name.
- `source_type`: delivery or provider class.
- `entity`: investigated subject or related subject.
- `title`: human-readable evidence title.
- `confidence`: float between 0 and 1.

Strongly recommended fields:

- `source_hint`: routing hint used by `SourceCatalog`.
- `summary`: short source-level summary.
- `url`: source URL when available.
- `published_at` or `observed_at`: date/time evidence was published or observed.
- `raw`: original structured fields retained for traceability.
- `evidence`: claim list extracted from the source.
- `risk_events`: provider-supplied risk-event hints, still treated as leads.

## 2. Source Types

Suggested `source_type` values:

- `official_platform`
- `rest_api`
- `search_engine`
- `web_page`
- `telegram_bot`
- `licensed_api`
- `local_file`

Delivery shape is neutral. A Telegram public service is acceptable only when the underlying data is public or user-authorized and the connector retains source metadata.

## 3. Evidence Rules

Every record should preserve:

- where it came from;
- when it was observed;
- what was claimed;
- how confident the connector is;
- whether the data is public, licensed, user-authorized, or unknown.

Never treat a missing result as proof of no risk. Empty retrieval is a coverage signal.

## 4. Investigation Packet

`/api/investigate`, `bin/investigate.py`, and the MCP tool return:

```json
{
  "type": "investigation_packet",
  "version": "0.5.0",
  "summary": {},
  "risk_brief": {},
  "profile_brief": {},
  "evidence_ledger": [],
  "monitoring_seed": {},
  "report_markdown": "",
  "graph": {},
  "next_actions": []
}
```

The packet is the public product contract. UI, plugin hosts, and report exporters should prefer this shape over ad hoc role outputs.

## 5. Quality Gate

Connector output should pass `core.record_quality.audit_standardized_records`.

Minimum checks:

- confidence is numeric and inside `[0, 1]`;
- source and title are present;
- URL or source description exists for auditability;
- records do not rely on fabricated values;
- high-sensitivity leads retain source and verification status.

## 6. Public Release Boundary

Public release connectors should only route:

- public data;
- licensed data;
- user-authorized data;
- deterministic fixtures.

Secrets, cookies, PATs, private browser profiles, and local collaboration databases must never be committed.
