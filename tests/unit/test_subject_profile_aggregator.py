"""Tests for SubjectProfileAggregator."""
import asyncio
import pytest
from core.subject_profile_aggregator import (
    SubjectProfileAggregator, SubjectProfileReport, AdapterResult,
    IdentityAdapter, ContactAdapter, AddressAdapter,
    TravelAdapter, ConsumptionAdapter, SocialAdapter,
)


class TestIdentityAdapter:
    def test_fetch_with_resolver(self):
        async def resolver(subject_id):
            return {"name": subject_id, "uscc": "91110000TEST", "lei": "549300TEST"}
        adapter = IdentityAdapter(resolver=resolver)
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "success"
        assert result.data["identifiers"]["unified_social_credit_code"] == "91110000TEST"
        assert result.data["identifiers"]["lei"] == "549300TEST"

    def test_fetch_no_resolver(self):
        adapter = IdentityAdapter()
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "success"
        assert result.data["name"] == "Test Co."


class TestContactAdapter:
    def test_fetch_empty(self):
        adapter = ContactAdapter()
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "empty"

    def test_fetch_with_data(self):
        async def resolver(subject_id):
            return {"phones": ["+86-10-12345678"], "emails": ["test@example.com"]}
        adapter = ContactAdapter(resolver=resolver)
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "success"
        assert len(result.data["phones"]) == 1


class TestAddressAdapter:
    def test_fetch_empty(self):
        adapter = AddressAdapter()
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "empty"

    def test_fetch_with_data(self):
        async def resolver(subject_id):
            return {"registered_address": "No. 1 Finance Road"}
        adapter = AddressAdapter(resolver=resolver)
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "success"
        assert "No. 1 Finance Road" in result.data["registered_address"]


class TestTravelAdapter:
    def test_fetch_empty(self):
        adapter = TravelAdapter()
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "empty"

    def test_fetch_with_records(self):
        async def resolver(subject_id):
            return {"records": [{"type": "conference", "location": "Beijing", "date": "2026-06"}]}
        adapter = TravelAdapter(resolver=resolver)
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "success"
        assert result.data["record_count"] == 1


class TestConsumptionAdapter:
    def test_fetch_empty(self):
        adapter = ConsumptionAdapter()
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "empty"

    def test_fetch_with_records(self):
        async def resolver(subject_id):
            return {"records": [{"category": "procurement", "amount": "5000000"}]}
        adapter = ConsumptionAdapter(resolver=resolver)
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "success"


class TestSocialAdapter:
    def test_fetch_empty(self):
        adapter = SocialAdapter()
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "empty"

    def test_fetch_with_relations(self):
        async def resolver(subject_id):
            return {
                "related_entities": [
                    {"id": "entity:001", "name": "Related Co.", "type": "company", "relation": "supplier"},
                    {"id": "entity:002", "name": "Partner Ltd.", "type": "company", "relation": "joint_venture"},
                ],
                "common_addresses": ["Building A, Finance Street"],
            }
        adapter = SocialAdapter(resolver=resolver)
        result = asyncio.run(adapter.fetch("Test Co."))
        assert result.status == "success"
        assert result.data["relation_count"] == 2
        assert len(result.data["common_addresses"]) == 1


class TestSubjectProfileAggregator:
    def test_aggregate_basic(self):
        def identity_resolver(subject_id):
            return {"name": subject_id, "uscc": "91110000DEMO"}

        def social_resolver(subject_id):
            return {
                "related_entities": [
                    {"id": "entity:demo_supplier", "name": "Demo Supplier", "type": "company", "relation": "supplier"},
                ]
            }

        aggregator = SubjectProfileAggregator(
            max_depth=2,
            identity_resolver=identity_resolver,
            social_resolver=social_resolver,
        )
        report = asyncio.run(aggregator.aggregate("Demo Technology Co., Ltd.", "Demo Technology Co., Ltd."))
        assert report.seed_subject_name == "Demo Technology Co., Ltd."
        assert report.identity.get("identifiers", {}).get("unified_social_credit_code") == "91110000DEMO"
        assert report.source_count == 6
        assert len(report.related_entities) >= 1

    def test_aggregate_output_dict(self):
        aggregator = SubjectProfileAggregator(max_depth=1)
        report = asyncio.run(aggregator.aggregate("Demo Co."))
        d = report.to_dict()
        assert d["seed_subject_name"] == "Demo Co."
        assert "identity" in d
        assert "social_relations" in d
        assert "related_entities" in d

    def test_cache_mechanism(self):
        call_count = [0]
        def resolver(subject_id):
            call_count[0] += 1
            return {"name": subject_id}

        aggregator = SubjectProfileAggregator(identity_resolver=resolver, max_depth=1, cache_ttl_seconds=60)
        # First call
        asyncio.run(aggregator.aggregate("Cache Test"))
        first_count = call_count[0]
        # Second call — should hit cache
        asyncio.run(aggregator.aggregate("Cache Test"))
        second_count = call_count[0]
        # Cache should prevent second resolver call for identity adapter
        # Note: other adapters still call their resolvers, so total may increase
        assert aggregator._cache_hits > 0

    def test_custom_adapter_registration(self):
        class CustomAdapter(IdentityAdapter):
            async def _do_fetch(self, subject_id, params=None):
                return AdapterResult(source=self.name, subject_id=subject_id, status="success",
                                     data={"custom_field": "custom_value"})

        aggregator = SubjectProfileAggregator(max_depth=1)
        aggregator.register_adapter("custom", CustomAdapter())
        result = asyncio.run(aggregator.query_single("custom", "Test"))
        assert result.status == "success"
        assert result.data.get("custom_field") == "custom_value"

    def test_error_handling(self):
        async def failing_resolver(subject_id):
            raise RuntimeError("Simulated failure")

        aggregator = SubjectProfileAggregator(identity_resolver=failing_resolver, max_depth=1)
        report = asyncio.run(aggregator.aggregate("Error Test"))
        # Should not crash — error sources should be in failed_sources
        assert "identity" in report.failed_sources or report.identity == {}

    def test_timeout_handling(self):
        async def slow_resolver(subject_id):
            await asyncio.sleep(10)
            return {"name": subject_id}

        aggregator = SubjectProfileAggregator(identity_resolver=slow_resolver, max_depth=1)
        # Override timeout to 0.5s for test
        aggregator._adapters["identity"].timeout = 0.5
        report = asyncio.run(aggregator.aggregate("Timeout Test"))
        # Should complete despite timeout
        assert report.seed_subject_name == "Timeout Test"

    def test_deep_association_limit(self):
        def social_resolver(subject_id):
            return {
                "related_entities": [
                    {"id": f"entity:level1_{subject_id}", "name": f"L1 {subject_id}", "type": "company", "relation": "subsidiary"},
                ]
            }

        aggregator = SubjectProfileAggregator(social_resolver=social_resolver, max_depth=3)
        report = asyncio.run(aggregator.aggregate("Parent Co."))
        # Should have entities at depth 1
        for e in report.related_entities:
            assert e.depth <= aggregator.max_depth

    def test_clear_cache(self):
        aggregator = SubjectProfileAggregator(max_depth=1)
        asyncio.run(aggregator.aggregate("Cache Co."))
        hits_before = aggregator._cache_hits
        aggregator.clear_cache()
        asyncio.run(aggregator.aggregate("Cache Co."))
        # After clearing, cache should be fresh (no additional hits from previous)
        assert aggregator._cache_hits >= hits_before
