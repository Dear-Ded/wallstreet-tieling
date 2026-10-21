# Registry additions for GdCreditCompanyLookup (Guangdong credit platform).
# Coordinator: paste the ConnectorCapability block into default_connector_capabilities()
# and merge IMPLEMENTATION_PACKS into _SOURCE_STRENGTHENING_IMPLEMENTATION_PACKS.

CONNECTOR_CAPABILITIES = '''
        ConnectorCapability(
            name="public_gd_credit_lookup",
            shape=ConnectorShape.REST_API,
            access=SourceAccess.PUBLIC,
            authority=SourceAuthority.OFFICIAL,
            domains=(RetrievalDomain.PEOPLE,),
            status=ConnectorStatus.EXPERIMENTAL,
            configurable_endpoint=False,
            health_check=True,
            standardized_records=True,
            default_enabled=False,
            notes=(
                "GdCreditCompanyLookup adapter (adapters.gd_credit_adapter).",
                "Guangdong public credit platform: official company registry data",
                "(name, credit code, legal rep, address, status, capital, industry).",
                "HYBRID: name search is browser-assisted (slider captcha);",
                "detail by MASTERDATAID is fully automatic (no captcha);",
                "hot-search list is fully automatic.",
                "3s interval. No credentials, no login.",
                "Default-off: explicit operator enablement required per source-admission policy.",
            ),
            risk_flags=("explicit_enable_required", "public_data_only", "browser_assisted"),
        ),
'''

IMPLEMENTATION_PACKS = {
    "public_gd_credit_lookup": {
        "type": "source_strengthening_implementation_pack",
        "target_files": [
            "adapters/gd_credit_adapter.py",
            "core/connector_registry.py",
            "tests/unit/test_gd_credit_adapter.py",
            "tests/unit/test_connector_registry.py",
        ],
        "acceptance_commands": [
            "python -m pytest tests/unit/test_gd_credit_adapter.py tests/unit/test_connector_registry.py -q",
        ],
        "field_contract": {
            "record_type": "gd_credit_record",
            "source_hint": "public_gd_credit_lookup",
            "required_fields": ["company_name", "credit_code"],
            "report_gate": "official registry data; associations are leads, not verified facts",
        },
        "operator_notes": [
            "query(keyword): browser-assisted (slider captcha on search).",
            "parse_browser_result(json): parse search JSON -> masterdataids.",
            "query_detail(masterdataid): fully automatic, no captcha.",
            "query_hot(): fully automatic hot-search list.",
        ],
        "runtime_companion": {
            "type": "source_strengthening_runtime_companion",
            "connector": "public_gd_credit_lookup",
            "source_hint": "public_gd_credit_lookup",
            "required_config": [],
            "record_type": "gd_credit_record",
            "subject_match_levels": ["exact", "strong", "review"],
            "promotion_gate": "official records feed association leads; identity requires corroboration",
            "focused_test": "tests/unit/test_gd_credit_adapter.py::test_query_detail_extracts_fields",
        },
    },
}
