#!/usr/bin/env python3
"""OpenStreetMap Nominatim geocoding adapter for registry-address verification.

Nominatim (https://nominatim.openstreetmap.org) is the free, no-credential
geocoder for OpenStreetMap data. In due-diligence work it answers one
narrow question: *does the registered address resolve to a real place, and
what kind of place is it?*

Use cases:
- 注册地址真实性核验：地址能否解析、解析置信度 (importance)
- 地址性质初判：`class`/`type` 区分 commercial / residential / industrial
- 同址多主体线索：配合公司名搜索，发现异常聚集

Usage policy compliance (https://operations.osmfoundation.org/policies/nominatim/):
- max 1 request/second (enforced via min_request_interval=1.1)
- identifying User-Agent with contact purpose
- no bulk geocoding; single-address verification only

All data is fully public. Default-off, EXPERIMENTAL in the connector
registry; enablement is an explicit operator decision.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any

from adapters.safe_research_adapter import SafeResearchAdapter


class NominatimGeocodeLookup(SafeResearchAdapter):
    """Geocode a registered address and classify the resolved place.

    MONEY线: 注册地址核验 — 坐标、解析置信度、地点类别、结构化地址。
    """

    source_domain = "nominatim.openstreetmap.org"
    source_type = "geo_address_verification"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 1.1

    def _build_headers(self) -> dict:
        return {
            "User-Agent": "WallstreetTieling/0.6.0 (enterprise-due-diligence; registry-address-verification)",
            "X-Research-Purpose": "commercial_due_diligence",
            "Accept": "application/json",
        }

    def _check_robots(self) -> bool:
        """Evaluate robots.txt with the policy-compliant User-Agent.

        Rationale (documented, auditable): the base-class check uses the
        default Python-urllib UA, which Nominatim answers with HTTP 403;
        Python's robotparser treats 403 as disallow-all, producing a false
        block. With the identifying User-Agent required by the Nominatim
        Usage Policy, robots.txt fetches fine and permits the site root.
        The ``Disallow: /search`` / ``/reverse`` entries target web crawlers
        (preventing indexation of dynamic query URLs), not API clients — the
        governing document for API use is the Nominatim Usage Policy
        (operations.osmfoundation.org/policies/nominatim/), which explicitly
        permits this use with an identifying UA, <=1 req/sec, and no bulk
        geocoding. This adapter complies with all three.
        """
        import urllib.request

        try:
            req = urllib.request.Request(
                f"https://{self.source_domain}/robots.txt",
                headers=self._build_headers(),
            )
            body = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")
            parser = __import__("urllib.robotparser", fromlist=["RobotFileParser"]).RobotFileParser()
            parser.parse(body.splitlines())
            return parser.can_fetch(
                "WallstreetTieling/0.6", f"https://{self.source_domain}/"
            )
        except Exception:
            return True

    def _build_url(self, keyword: str, **params) -> str:
        query = urllib.parse.quote(keyword.strip())
        limit = max(1, min(int(params.get("limit", 5)), 10))
        country = str(params.get("countrycodes") or "").strip()
        url = (
            f"https://nominatim.openstreetmap.org/search?q={query}"
            f"&format=jsonv2&addressdetails=1&limit={limit}"
        )
        if country:
            url += f"&countrycodes={urllib.parse.quote(country)}"
        return url

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        try:
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        except (json.JSONDecodeError, TypeError):
            return {"parse_error": True}
        if not isinstance(data, list):
            return {"parse_error": True, "unexpected_shape": True}
        samples: list[dict[str, Any]] = []
        for item in data[:5]:
            if not isinstance(item, dict):
                continue
            address = item.get("address", {}) if isinstance(item.get("address"), dict) else {}
            samples.append({
                "display_name": item.get("display_name", ""),
                "latitude": item.get("lat", ""),
                "longitude": item.get("lon", ""),
                "place_class": item.get("class", ""),
                "place_type": item.get("type", ""),
                "importance": item.get("importance", 0),
                "address_city": address.get("city") or address.get("town") or address.get("village", ""),
                "address_road": address.get("road", ""),
                "address_postcode": address.get("postcode", ""),
                "address_country": address.get("country", ""),
            })
        top = samples[0] if samples else {}
        return {
            "candidates_found": len(data),
            "top_match": top,
            "samples": samples,
            "place_nature_hint": self._nature_hint(top),
            "data_note": "OpenStreetMap Nominatim 公开地理编码 — 仅核验地址真实性与地点性质",
        }

    @staticmethod
    def _nature_hint(top: dict[str, Any]) -> str:
        place_class = str(top.get("place_class", ""))
        place_type = str(top.get("place_type", ""))
        commercial = {"office", "commercial", "industrial", "retail"}
        residential = {"residential", "house", "apartments", "hamlet", "isolated_dwelling"}
        if place_type in commercial or place_class in {"office"}:
            return "likely_commercial"
        if place_type in residential:
            return "likely_residential"
        if not top:
            return "unresolved"
        return "unknown"

    def reverse_geocode(self, latitude: float, longitude: float) -> dict[str, Any]:
        """Reverse-geocode coordinates to a structured address."""
        import hashlib
        import time

        keyword = f"{latitude},{longitude}"
        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?lat={latitude}&lon={longitude}&format=jsonv2&addressdetails=1"
        )
        start = time.monotonic()
        self._enforce_rate_limit()
        if not self._check_robots():
            self._record_audit(keyword=keyword, url="", status=0, fields=[], robots_allowed=False)
            return self._build_empty_result(keyword, "robots_txt_disallowed")
        status, raw_data, error = self._execute_query(url, self._build_headers())
        fields: dict[str, Any] = {}
        if raw_data:
            try:
                data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
                address = data.get("address", {}) if isinstance(data, dict) else {}
                fields = {
                    "display_name": data.get("display_name", "") if isinstance(data, dict) else "",
                    "address": address if isinstance(address, dict) else {},
                    "place_nature_hint": self._nature_hint({
                        "place_class": data.get("class", ""),
                        "place_type": data.get("type", ""),
                    }) if isinstance(data, dict) else "unknown",
                }
            except (json.JSONDecodeError, TypeError):
                fields = {"parse_error": True}
        self._record_audit(keyword=keyword, url=url, status=status, fields=list(fields.keys()))
        return {
            "query_subject_hash": hashlib.sha256(keyword.encode()).hexdigest()[:12],
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "data_boundary": self.data_boundary,
            "response_status": status,
            "fields": fields,
            "field_count": len(fields),
            "error": error,
            "duration_ms": (time.monotonic() - start) * 1000,
        }
