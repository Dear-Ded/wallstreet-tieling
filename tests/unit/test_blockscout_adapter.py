"""Tests for Blockscout on-chain counterparty adapter (offline fixtures)."""

import json

from adapters.blockscout_adapter import BlockscoutAddressLookup, _norm_addr

SEED = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
A = "0x1111111111111111111111111111111111111111"
B = "0x2222222222222222222222222222222222222222"

FIXTURE_TXS = json.dumps({
    "items": [
        {"from": {"hash": SEED}, "to": {"hash": A},
         "timestamp": "2026-10-20T10:00:00.000000Z"},
        {"from": {"hash": SEED}, "to": {"hash": A},
         "timestamp": "2026-10-21T10:00:00.000000Z"},
        {"from": {"hash": B}, "to": {"hash": SEED},
         "timestamp": "2026-10-19T10:00:00.000000Z"},
        {"from": {"hash": SEED}, "to": {"hash": SEED},  # 自转跳过
         "timestamp": "2026-10-18T10:00:00.000000Z"},
        {"from": {"hash": SEED}, "to": None,  # 合约创建跳过
         "timestamp": "2026-10-17T10:00:00.000000Z"},
    ],
    "next_page_params": {"block_number": 123},
})


def _adapter(body, status=200):
    return BlockscoutAddressLookup(
        execute_query=lambda url, headers: (status, body, ""),
        robots_checker=lambda domain, url: True,
        sleeper=lambda s: None,
    )


def test_build_url():
    a = _adapter("")
    url = a._build_url(SEED)
    assert url == f"https://eth.blockscout.com/api/v2/addresses/{SEED}/transactions"


def test_invalid_input_rejected():
    a = _adapter("")
    out = a.query("not-an-address")
    assert out["error"].startswith("invalid_input")


def test_extract_counterparties_ranked_and_directed():
    a = _adapter(FIXTURE_TXS)
    f = a.query(SEED)["fields"]
    assert f["transactions_scanned"] == 5
    assert f["unique_counterparties"] == 2
    cps = {c["address"]: c for c in f["counterparties"]}
    assert cps[A]["tx_count"] == 2 and cps[A]["sent"] == 2
    assert cps[B]["tx_count"] == 1 and cps[B]["received"] == 1
    assert f["counterparties"][0]["address"] == A  # 按次数排序
    assert cps[A]["first_seen"] == "2026-10-20T10:00:00.000000Z"
    assert cps[A]["last_seen"] == "2026-10-21T10:00:00.000000Z"
    assert "弱关联" in f["data_note"]
    assert f["explorer_url"] == f"https://eth.blockscout.com/address/{SEED}"


def test_extract_caps_at_top20():
    items = [{"from": {"hash": SEED},
              "to": {"hash": f"0x{i:040x}"},
              "timestamp": "2026-10-21T00:00:00Z"} for i in range(1, 40)]
    f = BlockscoutAddressLookup.parse_transactions(items, seed_hint=SEED)
    assert len(f["counterparties"]) == 20
    assert f["unique_counterparties"] == 39


def test_parse_without_seed_skips():
    f = BlockscoutAddressLookup.parse_transactions(
        [{"from": {"hash": A}, "to": {"hash": B}}], seed_hint="")
    assert f["unique_counterparties"] == 0


def test_extract_garbage():
    a = _adapter("not json{{{")
    assert a.query(SEED)["fields"]["parse_error"] is True


def test_extract_api_error_shape():
    a = _adapter(json.dumps({"errors": [{"title": "x"}]}))
    assert a.query(SEED)["fields"]["lookup_failed"] is True


def test_norm_addr():
    assert _norm_addr("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045") == SEED
    assert _norm_addr("0x123") == ""
    assert _norm_addr(None) == ""


def test_adapter_is_experimental_and_conservative():
    assert BlockscoutAddressLookup.min_request_interval >= 5.0
    assert BlockscoutAddressLookup.requires_credentials is False
    assert BlockscoutAddressLookup.data_boundary == "fully_public"
