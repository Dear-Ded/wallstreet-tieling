# Terminology Standard

Scope: `wallstreet-tieling` v0.5.0 Alpha.

This project is an enterprise intelligence and risk investigation product. Use
professional, evidence-bound language in code, docs, reports, and user-facing
copy. Do not use wording that implies unauthorized access, personal intrusion,
or unverified certainty.

## Standard Product Terms

| Avoid | Use |
|---|---|
| crawler/scraper as product copy | public web collection |
| hack, bypass, break through | authorized access, public-source retrieval, or fixture-backed validation |
| personal privacy mining | subject profile dimension |
| human flesh search | enterprise subject investigation |
| full parity | tested module parity or fixture-backed parity |
| confirmed fact from weak public snippets | public lead, candidate signal, or human-review lead |
| monitoring as current release | later-version monitoring baseline |
| AI generated conclusion | evidence-backed assessment |

## Chinese Copy Guidance

| Avoid | Use |
|---|---|
| 人肉搜索 | 企业主体调查 / 公开信息线索核验 |
| 爬虫破解 | 公开网页信息采集 / 授权数据接入 |
| 绕过验证 | 授权登录 / 人工核验 / 阻断状态记录 |
| 全量对标 | 当前版本已验证模块对标 |
| 已查实 | 已形成证据支持 / 待人工核验线索 |
| 持续监控已上线 | 后续版本监控基线 |

## Evidence Labels

- `fact`: admitted evidence with required fields and provenance.
- `lead`: relevant signal that is incomplete, weak, blocked, or needs review.
- `candidate`: possible entity, relation, controller, or risk event requiring
  stronger support.
- `fixture-backed`: validated through local test fixtures, not live production.
- `authorized-smoke`: validated through an allowed live or authenticated path.
- `template-only`: query or source plan exists, but no real retrieval was
  verified.

## Mandatory Boundaries

- Public, licensed, fixture-backed, or user-authorized evidence only.
- Weak public snippets do not create graph facts, controller facts, or report
  certainty.
- Continuous monitoring remains future scope for this release.
- QYYJT live/API parity must not be claimed without authorized smoke evidence.
- UI copy, persona presentation, and backend evidence generation should remain
  separable so visual work cannot weaken evidence quality.

## Related Documents

- `PROJECT_TASKBOARD.md`
- `docs/SEARCH_INTEGRATION_LEDGER.md`
- `docs/ENGINEERING_BLUEPRINT.md`
- `release/variants.yaml`
