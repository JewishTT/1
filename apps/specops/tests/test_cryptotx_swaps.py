"""Swap-provider contracts, exercised against deterministic transports.

Live endpoints are deliberately not called: a quote test that needs the internet
proves the internet is up, not that the adapter encodes the route correctly.
"""

from __future__ import annotations

import time
from dataclasses import replace
from decimal import Decimal

import httpx
import pytest
from eth_abi import encode as abi_encode
from eth_utils import keccak, to_checksum_address
from specops.cryptotx.config import clear_config_cache, get_config
from specops.cryptotx.errors import SwapUnavailable
from specops.cryptotx.models import Asset, Chain, Network
from specops.cryptotx.swaps.base import SwapRequest
from specops.cryptotx.swaps.evm import UniswapProvider, ZeroExProvider
from specops.cryptotx.swaps.router import SwapRouter
from specops.cryptotx.swaps.thorchain import ThorchainProvider
from specops.cryptotx.swaps.tron import SunSwapProvider
from tronpy.abi import trx_abi


@pytest.fixture(autouse=True)
def _clear_config():
    clear_config_cache()
    yield
    clear_config_cache()


def _config(**overrides):
    return replace(get_config(), **overrides)


BTC = Asset(Chain.BITCOIN, "BTC", 8)
ETH = Asset(Chain.ETHEREUM, "ETH", 18)
USDC = Asset(
    Chain.ETHEREUM,
    "USDC",
    6,
    "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238",
)
TRX = Asset(Chain.TRON, "TRX", 6)
USDT = Asset(Chain.TRON, "USDT", 6, "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
USDC_MAIN = Asset(
    Chain.ETHEREUM,
    "USDC",
    6,
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
)
EVM_A = "0x0000000000000000000000000000000000000001"
EVM_B = "0x0000000000000000000000000000000000000002"


def test_thorchain_btc_deposit_quote():
    expiry = int(time.time()) + 600

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/thorchain/quote/swap"
        assert request.url.params["from_asset"] == "BTC.BTC"
        assert request.url.params["to_asset"] == "ETH.ETH"
        return httpx.Response(
            200,
            json={
                "inbound_address": "bc1qvault",
                "router": "0xD37BbE5744D730a1d98d8DC97c42F0Ca46aD7146",
                "memo": f"=:ETH.ETH:{EVM_B}",
                "expiry": expiry,
                "expected_amount_out": "150000000000000000",
                "fees": {"total": "10000"},
            },
        )

    provider = ThorchainProvider(
        _config(), transport=httpx.MockTransport(handler)
    )
    quote = provider.quote(
        SwapRequest(
            from_chain=Chain.BITCOIN,
            to_chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            from_asset=BTC,
            to_asset=ETH,
            amount=Decimal("0.01"),
            from_address="bc1qsource",
            to_address=EVM_B,
            slippage_bps=500,
        )
    )
    provider.close()
    assert quote.expected_amount_out == Decimal("0.15")
    assert quote.min_amount_out == Decimal("0.1425")
    assert quote.instruction is not None
    assert quote.instruction.kind == "deposit"
    assert quote.instruction.to == "bc1qvault"
    assert quote.instruction.memo == f"=:ETH.ETH:{EVM_B}"
    assert quote.instruction.amount == Decimal("0.01")


def test_thorchain_eth_router_call_quote():
    expiry = int(time.time()) + 600
    router = "0xD37BbE5744D730a1d98d8DC97c42F0Ca46aD7146"
    vault = "0x0000000000000000000000000000000000000003"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "inbound_address": vault,
                "router": router,
                "memo": "=:BTC.BTC:bc1qdest",
                "expiry": expiry,
                "expected_amount_out": "100000",
                "fees": {"total": "1000000000000000"},
            },
        )

    provider = ThorchainProvider(
        _config(), transport=httpx.MockTransport(handler)
    )
    quote = provider.quote(
        SwapRequest(
            from_chain=Chain.ETHEREUM,
            to_chain=Chain.BITCOIN,
            network=Network.MAINNET,
            from_asset=ETH,
            to_asset=BTC,
            amount=Decimal("0.01"),
            from_address=EVM_A,
            to_address="bc1qdest",
        )
    )
    provider.close()
    instruction = quote.instruction
    assert instruction is not None
    assert instruction.kind == "evm_call"
    assert instruction.to == to_checksum_address(router)
    assert instruction.value == Decimal("0.01")
    assert instruction.calldata.startswith("0x")
    assert instruction.approval_spender is None
    assert quote.expected_amount_out == Decimal("0.001")
    assert quote.fee_native == Decimal("0.001")


class _Rpc:
    def __init__(self, amount_out: int) -> None:
        self.amount_out = amount_out
        self.calls = 0

    def call(self, method, params):
        assert method == "eth_call"
        self.calls += 1
        return "0x" + abi_encode(["uint256"], [self.amount_out]).hex()


class _EthAdapter:
    def __init__(self, rpc) -> None:
        self.network = Network.TESTNET
        self.rpc = rpc

    def validate_address(self, address: str) -> str:
        return to_checksum_address(address)


def test_uniswap_native_input_uses_wrap_and_multicall():
    router = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
    quoter = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
    cfg = _config(
        uniswap_router={Network.MAINNET: None, Network.TESTNET: router},
        uniswap_quoter={Network.MAINNET: None, Network.TESTNET: quoter},
    )
    rpc = _Rpc(200_000_000)
    adapter = _EthAdapter(rpc)
    provider = UniswapProvider(cfg, adapter, Network.TESTNET)
    quote = provider.quote(
        SwapRequest(
            from_chain=Chain.ETHEREUM,
            to_chain=Chain.ETHEREUM,
            network=Network.TESTNET,
            from_asset=ETH,
            to_asset=USDC,
            amount=Decimal("0.01"),
            from_address=EVM_A,
            to_address=EVM_B,
        )
    )
    assert quote.expected_amount_out == Decimal("200")
    assert rpc.calls == 4
    assert to_checksum_address(EVM_B)[2:].lower() in quote.instruction.calldata.lower()
    instruction = quote.instruction
    assert instruction is not None
    assert instruction.kind == "evm_call"
    assert instruction.value == Decimal("0.01")
    assert instruction.approval_spender is None
    assert instruction.extra["fee_tier"] == 500
    selector = keccak(
        text="exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))"
    )[:4].hex()
    assert instruction.calldata.startswith("0x" + selector)


def test_zeroex_quote_maps_transaction_and_approval():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/swap/v1/quote"
        assert request.headers["0x-api-key"] == "key"
        return httpx.Response(
            200,
            json={
                "buyAmount": "200000000",
                "minBuyAmount": "190000000",
                "to": "0x0000000000000000000000000000000000000009",
                "data": "0xdeadbeef",
                "value": "10000000000000000",
                "allowanceTarget": "0x0000000000000000000000000000000000000008",
                "estimatedGas": 250000,
            },
        )

    cfg = _config(zeroex_api_key="key")
    provider = ZeroExProvider(cfg, transport=httpx.MockTransport(handler))
    quote = provider.quote(
        SwapRequest(
            from_chain=Chain.ETHEREUM,
            to_chain=Chain.ETHEREUM,
            network=Network.MAINNET,
            from_asset=ETH,
            to_asset=USDC_MAIN,
            amount=Decimal("0.01"),
            from_address=EVM_A,
            to_address=EVM_A,
            slippage_bps=500,
        )
    )
    provider.close()
    assert quote.expected_amount_out == Decimal("200")
    assert quote.min_amount_out == Decimal("190")
    instruction = quote.instruction
    assert instruction is not None
    assert instruction.to == "0x0000000000000000000000000000000000000009"
    assert instruction.calldata == "0xdeadbeef"
    assert instruction.value == Decimal("0.01")
    assert instruction.approval_spender is None


class _TronClient:
    def __init__(self, amounts: list[int]) -> None:
        self.amounts = amounts
        self.calls = 0

    def trigger_const_smart_contract_function(
        self, owner, contract, function_selector, parameter
    ):
        assert function_selector == "getAmountsOut(uint256,address[])"
        self.calls += 1
        return trx_abi.encode_single("uint256[]", self.amounts).hex()


class _TronAdapter:
    def __init__(self, client) -> None:
        self.network = Network.MAINNET
        self._client = client

    def validate_address(self, address: str) -> str:
        return address

    def client(self):
        return self._client


def test_sunswap_native_input_quote_and_calldata():
    cfg = _config()
    client = _TronClient([1_000_000, 2_000_000])
    provider = SunSwapProvider(cfg, _TronAdapter(client), Network.MAINNET)
    quote = provider.quote(
        SwapRequest(
            from_chain=Chain.TRON,
            to_chain=Chain.TRON,
            network=Network.MAINNET,
            from_asset=TRX,
            to_asset=USDT,
            amount=Decimal("1"),
            from_address="TNUC9Qb1rRpS5CbWLmNMxXBjyFoydXjWFR",
            to_address="TNUC9Qb1rRpS5CbWLmNMxXBjyFoydXjWFR",
        )
    )
    assert client.calls == 1
    assert quote.expected_amount_out == Decimal("2")
    assert quote.min_amount_out == Decimal("1.99")
    instruction = quote.instruction
    assert instruction is not None
    assert instruction.kind == "tron_call"
    assert instruction.value == Decimal("1")
    assert instruction.fee_limit > 0
    assert instruction.approval_spender is None
    assert instruction.calldata.startswith("0x")

def test_router_does_not_escape_provider_allowlist():
    config = _config(enabled_swap_providers=("uniswap",))
    request = SwapRequest(
        from_chain=Chain.ETHEREUM,
        to_chain=Chain.ETHEREUM,
        network=Network.TESTNET,
        from_asset=ETH,
        to_asset=USDC,
        amount=Decimal("0.01"),
        from_address=EVM_A,
        to_address=EVM_A,
        providers=("zeroex",),
    )
    assert SwapRouter(config).attempts(request) == []


def test_sunswap_testnet_requires_explicit_wtrx(monkeypatch):
    monkeypatch.delenv("CRYPTOTX_WTRX_TESTNET", raising=False)
    provider = SunSwapProvider(_config(), object(), Network.TESTNET)
    with pytest.raises(SwapUnavailable, match="CRYPTOTX_WTRX_TESTNET"):
        provider._wtrx()


def test_zeroex_refuses_third_party_recipient():
    provider = ZeroExProvider(_config())
    request = SwapRequest(
        from_chain=Chain.ETHEREUM,
        to_chain=Chain.ETHEREUM,
        network=Network.MAINNET,
        from_asset=USDC_MAIN,
        to_asset=ETH,
        amount=Decimal("10"),
        from_address=EVM_A,
        to_address=EVM_B,
    )
    with pytest.raises(SwapUnavailable, match="third-party"):
        provider.quote(request)
    provider.close()