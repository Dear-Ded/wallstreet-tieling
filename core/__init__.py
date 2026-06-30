"""Public exports for wallstreet-tieling core primitives."""
from __future__ import annotations

from .financial_analyzer_v2 import (
    BusinessModelAnalysis,
    CashFlowAnalysis,
    EarningsQualityAnalysis,
    EnhancedFinancialAnalyzer,
    FinancialHealthGrade,
    FinancialRatio,
    FinancialRisk,
)
from .industry_intelligence import (
    IndustryIntelligenceEngine,
    IndustryIntelligenceReport,
    IndustryLifecycle,
    IndustrySignal,
    IndustryThreatLevel,
)
from .enterprise_strategy import (
    EnterpriseSegment,
    EnterpriseStrategyEngine,
    EnterpriseStrategyReport,
)
from .connector_registry import (
    ConnectorCapability,
    ConnectorRegistry,
    ConnectorStatus,
    default_connector_capabilities,
)
from .adapter_audit import AdapterAuditRow, AdapterAuditor
from .source_admission import (
    AdmissionDecision,
    AdmissionInput,
    AdmissionPolicy,
    AdmissionReport,
    DataSourceTier,
    SourceAdmissionEvaluator,
)
from .enterprise_cognition import EnterpriseCognitionEngine, EnterpriseCognitionProfile
from .context_budget import ContextBudgetManager, ContextCapsule
from .datasource_fixtures import DatasourceFixturePack, build_datasource_fixture_pack
from .interfaces import LLMProvider, LLMResponse, OutputProvider, PlatformAdapter, ToolProvider, ToolResult
from .intelligence_retrieval import (
    EvidenceGraph,
    EvidenceIngestor,
    EvidenceItem,
    EntityKind,
    InvestigativeRetrievalPlanner,
    InvestigationEntity,
    InvestigationRelation,
    RetrievalDomain,
    RetrievalPlan,
    RiskEvent,
    RiskSeverity,
    RiskSignalDetector,
    SearchTask,
)
from .product_intelligence import (
    ProductIntelligenceEngine,
    ProductIntelligenceReport,
    ProductLifecycle,
    ProductRiskLevel,
)
from .risk_event_store import RiskEventStore, StoredRiskEvent
from .risk_monitor import (
    RiskMonitor,
    RiskMonitorRun,
    RiskMonitorRunStore,
    default_monitor_run_store_path,
    run_monitor_once,
)
from .risk_discovery_pipeline import (
    RiskDiscoveryPipeline,
    RiskDiscoveryResult,
    offline_enforcement_fixture,
)
from .risk_graph_export import RiskGraphExport, export_risk_graph
from .subject_profile import (
    RecursionPolicy,
    SignalSensitivity,
    SubjectProfile,
    SubjectProfileBuilder,
    SubjectProfileDimension,
    SubjectProfileSignal,
    VerificationStatus,
)
from .roles import AUTHORITIES, RoleAuthority
from .rules import MODE_TEMPLATES, NO_FABRICATION_RULE, NO_FABRICATION_TAGLINE
from .supervision import SupervisionEvent, WuDehouSupervisor

__all__ = [
    "AUTHORITIES",
    "AdapterAuditRow",
    "AdapterAuditor",
    "AdmissionDecision",
    "AdmissionInput",
    "AdmissionPolicy",
    "AdmissionReport",
    "BusinessModelAnalysis",
    "CashFlowAnalysis",
    "ConnectorCapability",
    "ConnectorRegistry",
    "ConnectorStatus",
    "ContextBudgetManager",
    "ContextCapsule",
    "default_connector_capabilities",
    "default_monitor_run_store_path",
    "DataSourceTier",
    "DatasourceFixturePack",
    "EarningsQualityAnalysis",
    "Engine",
    "EvidenceGraph",
    "EvidenceIngestor",
    "EvidenceItem",
    "EntityKind",
    "EnhancedFinancialAnalyzer",
    "FinancialHealthGrade",
    "FinancialRatio",
    "FinancialRisk",
    "EnterpriseSegment",
    "EnterpriseCognitionEngine",
    "EnterpriseCognitionProfile",
    "EnterpriseStrategyEngine",
    "EnterpriseStrategyReport",
    "IndustryIntelligenceEngine",
    "IndustryIntelligenceReport",
    "IndustryLifecycle",
    "IndustrySignal",
    "IndustryThreatLevel",
    "InvestigativeRetrievalPlanner",
    "InvestigationPacket",
    "InvestigationEntity",
    "InvestigationRelation",
    "LLMProvider",
    "LLMResponse",
    "MODE_TEMPLATES",
    "NO_FABRICATION_RULE",
    "NO_FABRICATION_TAGLINE",
    "OutputProvider",
    "PlatformAdapter",
    "ProductIntelligenceEngine",
    "ProductIntelligenceReport",
    "ProductLifecycle",
    "ProductRiskLevel",
    "RecursionPolicy",
    "RetrievalDomain",
    "RetrievalPlan",
    "RiskEvent",
    "RiskDiscoveryPipeline",
    "RiskDiscoveryResult",
    "RiskEventStore",
    "RiskGraphExport",
    "RiskMonitor",
    "RiskMonitorRun",
    "RiskMonitorRunStore",
    "RiskSeverity",
    "RiskSignalDetector",
    "RoleAuthority",
    "SearchTask",
    "SignalSensitivity",
    "SourceAdmissionEvaluator",
    "StoredRiskEvent",
    "SubjectProfile",
    "SubjectProfileBuilder",
    "SubjectProfileDimension",
    "SubjectProfileSignal",
    "SupervisionEvent",
    "ToolProvider",
    "ToolResult",
    "VerificationStatus",
    "WuDehouSupervisor",
    "build_datasource_fixture_pack",
    "build_investigation_packet",
    "export_risk_graph",
    "offline_enforcement_fixture",
    "run_monitor_once",
]


def __getattr__(name: str):
    if name == "Engine":
        from .engine import Engine

        return Engine
    if name in {"InvestigationPacket", "build_investigation_packet"}:
        from .investigation import InvestigationPacket, build_investigation_packet

        return {
            "InvestigationPacket": InvestigationPacket,
            "build_investigation_packet": build_investigation_packet,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
