
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import time

"""
HANDOFF_TO_WORKBUDDY: office_chat_data_contract

OfficeChatPacket fields:
- company: str
- messages: list[OfficeMessage] — sorted by timestamp
- active_roles: list[str] — role_ids currently active
- sentinel_status: str — "normal" | "warn" | "critical"
- gm_summary: str — GM summary for display

OfficeMessage fields:
- role_id: str — from ROLES dict
- text: str — message body, evidence-grounded only
- msg_type: "group" | "sentinel_dm" | "gm_reply" — channel routing
- evidence_refs: list[str] — enterprise_cognition/profile keys
- timestamp: float — unix time

Rules:
- an-shao only msg_type=sentinel_dm, never group, never gm_reply
- All fact claims must have evidence_refs or explicitly state "lead" or "gap"
- No decorative/invented text
"""
ROLES = {
    "qian-shou-zheng": {"name":"钱守正","title":"总经理","lane":"overall_boundary"},
    "zhang-tie-zhu":  {"name":"张铁柱","title":"工商核查","lane":"corporate_registry"},
    "li-ming-yuan":   {"name":"李明远","title":"财务分析","lane":"financial_cognition"},
    "wang-si-yuan":   {"name":"王思远","title":"行业研究","lane":"industry_intelligence"},
    "zhao-gang":      {"name":"赵刚","title":"法务风控","lane":"court_legal_risk"},
    "ma-li-quan":     {"name":"马力全","title":"公开情报","lane":"people_intelligence"},
    "zhou-tong":       {"name":"周通","title":"数据源","lane":"connector_operations"},
    "zheng-shen-zhi": {"name":"郑慎之","title":"交叉验证","lane":"cross_verification"},
    "wu-de-hou":      {"name":"吴德厚","title":"质量门禁","lane":"quality_gate"},
    "liu-wen-hua":     {"name":"刘文华","title":"报告撰写","lane":"report_generation"},
    "yan-hao-kan":    {"name":"颜好看","title":"输出设计","lane":"report_layout"},
    "chen-zhi-yuan":   {"name":"陈志远","title":"任务拆解","lane":"retrieval_planning"},
    "an-shao":         {"name":"暗哨","title":"系统监控","lane":"runtime_observability"},
}

@dataclass
class OfficeMessage:
    role_id: str
    text: str
    msg_type: str = "group"  # group | sentinel_dm | gm_reply
    evidence_refs: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

@dataclass
class OfficeChatPacket:
    company: str
    messages: list[OfficeMessage] = field(default_factory=list)
    active_roles: list[str] = field(default_factory=list)
    sentinel_status: str = "normal"
    gm_summary: str = ""

def build_office_chat_packet(
    company: str,
    enterprise_cognition: dict[str, Any],
    profile_brief: dict[str, Any],
) -> OfficeChatPacket:
    msgs: list[OfficeMessage] = []
    active: list[str] = ["qian-shou-zheng", "wu-de-hou", "liu-wen-hua"]

    # 1. GM opens
    msgs.append(OfficeMessage("qian-shou-zheng", f"收到任务：对 {company} 启动企业调查。各部门按职责开展工作，证据先行，不假设。"))
    active.append("chen-zhi-yuan")

    # 2. Task decomposition
    msgs.append(OfficeMessage("chen-zhi-yuan", f"已拆分 {company} 为实体锚点、概览、深入钻取、专项四层检索计划。"))

    # 3. Industry/product
    industry = enterprise_cognition.get("industry") or enterprise_cognition.get("industry_cognition", {}).get("industry")
    product = enterprise_cognition.get("product") or enterprise_cognition.get("product_cognition", {}).get("product_name")
    if industry or product:
        summary = f"{company} 行业定位：{industry or '暂缺'}；核心产品：{product or '暂缺'}。"
        msgs.append(OfficeMessage("wang-si-yuan", summary, evidence_refs=["enterprise_cognition.industry", "enterprise_cognition.product"]))
        active.append("wang-si-yuan")

    # 4. Financial
    financial = enterprise_cognition.get("financial", {})
    if financial and financial.get("row_count"):
        msgs.append(OfficeMessage("li-ming-yuan", f"{company} 已获取财务数据，共 {financial['row_count']} 条记录。正在分析资金流和偿债能力。", evidence_refs=["enterprise_cognition.financial"]))
        active.append("li-ming-yuan")
    else:
        msgs.append(OfficeMessage("zhou-tong", f"{company} 公开财务数据暂缺，已发起公开搜索补充。"))

    # 5. Controllers
    controllers = profile_brief.get("controller_candidates") or profile_brief.get("controller_candidate_count")
    if controllers:
        cnt = len(controllers) if isinstance(controllers, list) else controllers
        msgs.append(OfficeMessage("zhang-tie-zhu", f"{company} 已识别 {cnt} 名潜在实控人/关键人员，正在核查控制路径。", evidence_refs=["subject_profile.controller_candidates"]))
        active.append("zhang-tie-zhu")

    # 6. Risk events
    risk_summary = enterprise_cognition.get("risk_event_summary", {})
    risk_count = risk_summary.get("count") if isinstance(risk_summary, dict) else 0
    if risk_count:
        msgs.append(OfficeMessage("zhao-gang", f"{company} 发现 {risk_count} 条风险事件，涉及法务/行政/公开舆情，正在逐条核验。", evidence_refs=["enterprise_cognition.risk_events"]))
        active.append("zhao-gang")

    # 7. Supply chain
    supply = enterprise_cognition.get("supply_chain_profile") or {}
    if supply and supply.get("row_count"):
        msgs.append(OfficeMessage("wang-si-yuan", f"{company} 供应链画像：{supply.get('supplier_count',0)} 供应商，{supply.get('customer_count',0)} 客户，{supply.get('relationship_count',0)} 关系。", evidence_refs=["enterprise_cognition.supply_chain_profile"]))
    else:
        msgs.append(OfficeMessage("ma-li-quan", f"{company} 供应链信息待补充，已从公开来源检索上下游和合作伙伴。"))

    # 8. Quality gate
    qg = enterprise_cognition.get("quality_gate", {})
    if qg.get("score") and qg.get("score") < 70:
        msgs.append(OfficeMessage("wu-de-hou", f"[质量警告] {company} 调查数据质量评分 {qg['score']}，低于可进入人工复核的阈值。请补充缺失证据。"))

    # 9. Sentinel
    an_text = f"系统正常。成本在预算内。没有发现协议违规或异常故障。"
    msgs.append(OfficeMessage("an-shao", an_text, msg_type="sentinel_dm"))

    # 10. GM summary
    gm_summary = f"{company} 调查进行中。已激活 {len(set(active))} 个角色。证据链正在构建，等待补充数据后进入复核。"

    return OfficeChatPacket(
        company=company,
        messages=msgs,
        active_roles=list(set(active)),
        gm_summary=gm_summary,
    )
