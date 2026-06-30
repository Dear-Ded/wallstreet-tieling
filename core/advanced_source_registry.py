"""
企业尽调适配器管线集成 — 向investigation引擎注册可用的高级数据源。
所有高级数据源默认不接入默认一键尽调流程,需用户显式授权。
"""

from typing import Any

# 所有高级数据源注册表 — 默认不接入 build_investigation_packet
ADVANCED_SOURCE_REGISTRY: dict[str, dict[str, Any]] = {
    "enterprise_profiling": {
        "module": "adapters.enterprise_profiling",
        "classes": [
            "ExecutiveIdentityVerification",
            "EnterpriseDomainSecurityAssessment",
            "EnterpriseContactAttribution",
            "KeyPersonnelRecordCrossCheck",
        ],
        "default_enabled": False,       # 默认不接入一键尽调
        "requires_gate": True,           # 需要 UserAuthorizationGate
        "investigation_lanes": ["people", "money", "goods"],
        "description": "企业关键人员公开身份验证/企业域名安全评估/联系归属验证/公开记录交叉核验",
    },
    "authorized_overseas": {
        "module": "adapters.authorized_sources",
        "classes": [
            "AuthorizedCompaniesHouseLookup",
            "AuthorizedSECEdgarLookup",
            "AuthorizedOpenSanctionsLookup",
        ],
        "default_enabled": False,
        "requires_gate": True,
        "requires_api_key": True,
        "investigation_lanes": ["money", "registry"],
        "description": "海外公开注册/制裁合规查询(需用户提供API Key)",
    },
    "internet_asset_scan": {
        "module": "adapters.runtime_lookups_v2",
        "classes": [
            "EnterpriseAssetLookup",
            "DomainReputationLookup",
            "PublicRecordSecurityLookup",
        ],
        "default_enabled": False,
        "requires_gate": False,          # runtime_lookups_v2 是自主适配器(旧架构)
        "investigation_lanes": ["goods", "money"],
        "description": "企业信息技术资产可见性查询/域名公开声誉查询/信息安全公开记录查询",
    },
}


def get_available_advanced_sources() -> list[str]:
    """返回所有可用的高级数据源名称"""
    return list(ADVANCED_SOURCE_REGISTRY.keys())


def is_source_enabled_by_default(source_key: str) -> bool:
    """检查数据源是否默认启用(接入一键尽调)"""
    entry = ADVANCED_SOURCE_REGISTRY.get(source_key)
    return entry.get("default_enabled", False) if entry else False


def get_sources_for_lane(lane: str) -> list[str]:
    """返回特定调查线可用的高级数据源"""
    return [
        key for key, entry in ADVANCED_SOURCE_REGISTRY.items()
        if lane in entry.get("investigation_lanes", [])
    ]
