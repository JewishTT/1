"""Adapter factory and asset resolution."""

from __future__ import annotations

from typing import Any

import httpx

from specops.cryptotx.chains.base import ChainAdapter
from specops.cryptotx.chains.bitcoin import BitcoinAdapter
from specops.cryptotx.chains.ethereum import EthereumAdapter
from specops.cryptotx.chains.tron import TronAdapter
from specops.cryptotx.config import CryptoTxConfig, get_config
from specops.cryptotx.models import Asset, Chain, Network, resolve_asset

_ADAPTERS = {
    Chain.ETHEREUM: EthereumAdapter,
    Chain.TRON: TronAdapter,
    Chain.BITCOIN: BitcoinAdapter,
}


def make_adapter(
    chain: Chain,
    network: Network,
    *,
    config: CryptoTxConfig | None = None,
    transport: httpx.BaseTransport | None = None,
) -> ChainAdapter:
    cfg = config or get_config()
    if not cfg.mainnet_permitted(network):
        raise ValueError(
            "mainnet is disabled; set CRYPTOTX_ALLOW_MAINNET=1 to enable it"
        )
    cls = _ADAPTERS[chain]
    if chain is Chain.ETHEREUM:
        return cls(cfg, network, transport=transport)  # type: ignore[call-arg]
    if chain is Chain.BITCOIN:
        return cls(cfg, network, transport=transport)  # type: ignore[call-arg]
    return cls(cfg, network)  # type: ignore[call-arg]


def asset_for(
    chain: Chain,
    network: Network,
    symbol: str,
    params: dict[str, Any] | None = None,
) -> Asset:
    params = params or {}
    return resolve_asset(
        chain,
        network,
        symbol,
        contract=params.get("token") or params.get("contract"),
        decimals=params.get("decimals"),
    )
