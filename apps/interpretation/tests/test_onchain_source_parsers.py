from __future__ import annotations

import json
import sys
from pathlib import Path

APPS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APPS / "acquisition"))

from parsers.families import parse_source
from sources.catalogue import CATALOGUE_ROOT, load_source


CHAIN_DIR = CATALOGUE_ROOT / "10_blockchain"


def parse(name: str, payload: dict):
    source = load_source(CHAIN_DIR / f"{name}.yaml")
    return parse_source(source, json.dumps(payload).encode(), status_code=200)


def test_blockstream_transaction_detail_preserves_explicit_utxo_parent_refs() -> None:
    txid = "a" * 64
    parent = "b" * 64
    outcome = parse(
        "blockstream_btc_tx_detail",
        {
            "txid": txid,
            "fee": 800,
            "size": 220,
            "weight": 880,
            "status": {"confirmed": True, "block_height": 800000, "block_time": 1700000000},
            "vin": [
                {"txid": parent, "prevout": {"scriptpubkey_address": "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"}},
            ],
            "vout": [
                {"scriptpubkey_address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"},
            ],
        },
    )
    assert outcome.status == "ok"
    assert outcome.record_count == 1
    assert outcome.records[0].all_of("txid") == (txid,)
    assert outcome.records[0].all_of("input_txids") == (parent,)
    assert outcome.records[0].all_of("input_addresses") == ("1BoatSLRHtKNngkdXEeobR76b53LETtpyT",)
    assert outcome.records[0].all_of("output_addresses") == ("bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",)


def test_blockscout_address_metadata_extracts_address_and_native_balance() -> None:
    address = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
    outcome = parse(
        "blockscout_eth_address",
        {
            "hash": address,
            "coin_balance": "123456789",
            "transactions_count": 42,
            "is_contract": False,
            "name": None,
            "creation_transaction_hash": None,
        },
    )
    assert outcome.status == "ok"
    assert outcome.records[0].all_of("address") == (address,)
    assert outcome.records[0].all_of("balance_wei") == ("123456789",)


def test_blockscout_transactions_extracts_first_page_records() -> None:
    tx_hash = "0x" + "a" * 64
    from_address = "0x" + "b" * 40
    to_address = "0x" + "c" * 40
    outcome = parse(
        "blockscout_eth_transactions",
        {
            "items": [{
                "hash": tx_hash,
                "from": {"hash": from_address},
                "to": {"hash": to_address},
                "value": "5000",
                "block": 21000000,
                "timestamp": "2026-10-31T10:00:00.000000Z",
                "gas_used": "21000",
                "gas_price": "2000000000",
                "result": "success",
            }],
            "next_page_params": {"index": 21000000, "items_count": 50},
        },
    )
    assert outcome.status == "ok"
    assert outcome.record_count == 1
    assert outcome.records[0].all_of("tx_hash") == (tx_hash,)
    assert outcome.records[0].all_of("from_address") == (from_address,)
    assert outcome.records[0].all_of("to_address") == (to_address,)


def test_trongrid_account_uses_explicit_data_array_index() -> None:
    address = "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj"
    outcome = parse(
        "trongrid_account",
        {"data": [{
            "address": address,
            "balance": 100000000,
            "create_time": 1600000000000,
            "latest_operation_time": 1700000000000,
            "account_resource": {"energy_usage": 1},
        }]},
    )
    assert outcome.status == "ok"
    assert outcome.records[0].all_of("address") == (address,)
    assert outcome.records[0].all_of("balance_sun") == ("100000000",)


def test_trongrid_transaction_feed_reads_nested_contract_fields_without_guessing() -> None:
    txid = "d" * 64
    owner = "41" + "a" * 40
    to = "41" + "b" * 40
    outcome = parse(
        "trongrid_account_transactions",
        {"data": [{
            "txID": txid,
            "block_timestamp": 1700000000000,
            "blockNumber": 60000000,
            "raw_data": {
                "contract": [{
                    "parameter": {"value": {
                        "owner_address": owner,
                        "to_address": to,
                        "amount": 2500000,
                    }}
                }]
            },
            "ret": [{"contractRet": "SUCCESS"}],
        }]},
    )
    assert outcome.status == "ok"
    assert outcome.record_count == 1
    assert outcome.records[0].all_of("tx_id") == (txid,)
    assert outcome.records[0].all_of("owner_address") == (owner,)
    assert outcome.records[0].all_of("to_address") == (to,)
