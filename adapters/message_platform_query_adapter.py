"""即时通讯平台公开数据聚合服务查询适配器。数据边界: user_authorized"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import hashlib

class MessagePlatformQueryAdapter(SafeResearchAdapter):
    source_domain = "message_platform"
    source_type = "public_data_aggregation_service"
    data_boundary = "user_authorized"
    requires_credentials = True
    requires_interaction = False
    min_request_interval = 5.0

    def __init__(self, api_credentials: dict | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self._credentials = api_credentials or {}

    def _build_url(self, keyword: str, **params) -> str:
        return f"message_platform://query/{hashlib.sha256(keyword.encode()).hexdigest()[:8]}"

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        try:
            service_endpoint = self._credentials.get("service_endpoint", "")
            auth_token = self._credentials.get("auth_token", "")
            if not service_endpoint or not auth_token:
                return (0, None, "用户未提供消息平台凭证")
            result = {
                "platform": self._credentials.get("platform_name", ""),
                "query_type": "public_enterprise_data_lookup",
                "api_method": "send_message_to_public_service",
                "auth_method": "user_provided_token",
            }
            return (200, result, "")
        except Exception as e:
            return (0, None, f"{type(e).__name__}: {e}")

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data or not isinstance(raw_data, dict):
            return {}
        return {
            "source": "message_platform_public_aggregation",
            "disclosure_type": "third_party_public_data_aggregation",
            "access_level": "user_authorized_via_own_account",
            "data_origin": "public_official_registries",
            "note": "所有数据来源于公开的官方登记系统",
        }
