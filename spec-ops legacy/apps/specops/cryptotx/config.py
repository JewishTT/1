"""Configuration for the crypto transaction fabric.

Two defaults are deliberate and load-bearing:

* **testnet everywhere.** A wallet is created on Sepolia / Nile / Bitcoin testnet
  unless the operator explicitly opts into mainnet. The network is part of every
  plan node, so a testnet plan cannot silently settle on mainnet.
* **dry-run everywhere.** Preparing and signing a transaction is always allowed;
  broadcasting it needs ``dry_run=False`` *and* a valid HMAC approval token over
  the plan digest. That token can only be minted when ``CRYPTOTX_APPROVAL_SECRET``
  is configured, so an unconfigured deployment cannot move funds at all.

No accessor here returns a secret. Readiness reports ``configured: true/false``
and the environment variable that would complete it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from specops.cryptotx.models import Chain, Network

REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DIR = REPO_ROOT / "logs" / "cryptotx"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _flag(name: str, default: bool = False) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _decimal(name: str, default: str) -> Decimal:
    try:
        return Decimal(_env(name, default) or default)
    except Exception as exc:  # noqa: BLE001 - a bad value must fail at boot, by name
        raise ValueError(f"{name} is not a decimal") from exc


def _network_map(mainnet: str, testnet: str, *, prefix: str) -> dict[Network, str]:
    return {
        Network.MAINNET: _env(f"{prefix}_MAINNET_URL", mainnet) or mainnet,
        Network.TESTNET: _env(f"{prefix}_TESTNET_URL", testnet) or testnet,
    }


@dataclass(frozen=True, slots=True)
class CryptoTxConfig:
    data_dir: Path
    vault_path: Path
    state_path: Path
    allow_mainnet: bool
    dry_run_default: bool
    approval_secret: str | None
    approval_ttl_s: int
    eth_rpc: dict[Network, str]
    tron_endpoint: dict[Network, str]
    tron_api_key: str | None
    btc_esplora: dict[Network, str]
    thorchain_url: str
    zeroex_url: str
    zeroex_api_key: str | None
    uniswap_router: dict[Network, str | None]
    uniswap_quoter: dict[Network, str | None]
    sunswap_router: dict[Network, str | None]
    swap_slippage_bps: int
    max_tx_native: dict[Chain, Decimal]
    max_total_native: dict[Chain, Decimal]
    min_gas_reserve: dict[Chain, Decimal]
    allowed_destinations: frozenset[str]
    require_allowlist: bool
    request_timeout_s: float
    max_retries: int
    enabled_swap_providers: tuple[str, ...]
    extra: dict[str, str] = field(default_factory=dict)

    def rpc_for(self, chain: Chain, network: Network) -> str:
        if chain is Chain.ETHEREUM:
            return self.eth_rpc[network]
        if chain is Chain.TRON:
            return self.tron_endpoint[network]
        return self.btc_esplora[network]

    def mainnet_permitted(self, network: Network) -> bool:
        return network is Network.TESTNET or self.allow_mainnet

    def provider_configured(self, name: str) -> bool:
        if name == "uniswap":
            return bool(
                self.uniswap_router[Network.MAINNET]
                or self.uniswap_router[Network.TESTNET]
            )
        if name == "sunswap":
            return bool(
                self.sunswap_router[Network.MAINNET]
                or self.sunswap_router[Network.TESTNET]
            )
        if name == "thorchain":
            return bool(self.thorchain_url)
        if name == "zeroex":
            return bool(self.zeroex_url)
        return False

    def readiness(self) -> dict[str, object]:
        return {
            "data_dir": str(self.data_dir),
            "vault": self.vault_path.exists(),
            "allow_mainnet": self.allow_mainnet,
            "dry_run_default": self.dry_run_default,
            "approval_configured": bool(self.approval_secret),
            "rpc": {
                chain.value: {network.value: self.rpc_for(chain, network) for network in Network}
                for chain in Chain
            },
            "swap_providers": {
                name: {"enabled": name in self.enabled_swap_providers,
                       "configured": self.provider_configured(name)}
                for name in ("thorchain", "uniswap", "sunswap", "zeroex")
            },
            "policy": {
                "max_tx_native": {k.value: str(v) for k, v in self.max_tx_native.items()},
                "max_total_native": {k.value: str(v) for k, v in self.max_total_native.items()},
                "min_gas_reserve": {k.value: str(v) for k, v in self.min_gas_reserve.items()},
                "allowed_destinations": len(self.allowed_destinations),
                "require_allowlist": self.require_allowlist,
            },
        }


@lru_cache(maxsize=1)
def get_config() -> CryptoTxConfig:
    data_dir = Path(_env("CRYPTOTX_DATA_DIR", str(_DEFAULT_DIR)) or str(_DEFAULT_DIR))
    endpoints = _network_map(
        "https://ethereum-rpc.publicnode.com",
        "https://ethereum-sepolia-rpc.publicnode.com",
        prefix="CRYPTOTX_ETH",
    )
    tron = _network_map(
        "https://api.trongrid.io", "https://nile.trongrid.io", prefix="CRYPTOTX_TRON"
    )
    btc = _network_map(
        "https://blockstream.info/api",
        "https://blockstream.info/testnet/api",
        prefix="CRYPTOTX_BTC",
    )
    allowed = frozenset(
        item.strip().lower()
        for item in (_env("CRYPTOTX_ALLOWED_DESTINATIONS", "") or "").split(",")
        if item.strip()
    )
    providers = tuple(
        item.strip().lower()
        for item in (_env("CRYPTOTX_SWAP_PROVIDERS", "thorchain,uniswap,sunswap") or "").split(",")
        if item.strip()
    )
    return CryptoTxConfig(
        data_dir=data_dir,
        vault_path=Path(_env("CRYPTOTX_VAULT_PATH", str(data_dir / "vault.json")) or ""),
        state_path=Path(_env("CRYPTOTX_STATE_PATH", str(data_dir / "state.sqlite3")) or ""),
        allow_mainnet=_flag("CRYPTOTX_ALLOW_MAINNET", False),
        dry_run_default=not _flag("CRYPTOTX_LIVE_BY_DEFAULT", False),
        approval_secret=_env("CRYPTOTX_APPROVAL_SECRET"),
        approval_ttl_s=int(_env("CRYPTOTX_APPROVAL_TTL_S", "900") or "900"),
        eth_rpc=endpoints,
        tron_endpoint=tron,
        tron_api_key=_env("CRYPTOTX_TRON_API_KEY"),
        btc_esplora=btc,
        thorchain_url=_env("CRYPTOTX_THORCHAIN_URL", "https://thornode.ninerealms.com")
        or "https://thornode.ninerealms.com",
        zeroex_url=_env("CRYPTOTX_ZEROEX_URL", "https://api.0x.org")
        or "https://api.0x.org",
        zeroex_api_key=_env("CRYPTOTX_ZEROEX_API_KEY"),
        uniswap_router={
            Network.MAINNET: _env(
                "CRYPTOTX_UNISWAP_ROUTER_MAINNET", "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"
            ),
            Network.TESTNET: _env("CRYPTOTX_UNISWAP_ROUTER_TESTNET"),
        },
        uniswap_quoter={
            Network.MAINNET: _env(
                "CRYPTOTX_UNISWAP_QUOTER_MAINNET", "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"
            ),
            Network.TESTNET: _env("CRYPTOTX_UNISWAP_QUOTER_TESTNET"),
        },
        sunswap_router={
            Network.MAINNET: _env(
                "CRYPTOTX_SUNSWAP_ROUTER_MAINNET", "TKzxdSv2FZKQrEqkKVgp5DcwEXBEKMg2Ax"
            ),
            Network.TESTNET: _env("CRYPTOTX_SUNSWAP_ROUTER_TESTNET"),
        },
        swap_slippage_bps=int(_env("CRYPTOTX_SLIPPAGE_BPS", "50") or "50"),
        max_tx_native={
            Chain.ETHEREUM: _decimal("CRYPTOTX_MAX_TX_ETH", "0.5"),
            Chain.TRON: _decimal("CRYPTOTX_MAX_TX_TRX", "1000"),
            Chain.BITCOIN: _decimal("CRYPTOTX_MAX_TX_BTC", "0.1"),
        },
        max_total_native={
            Chain.ETHEREUM: _decimal("CRYPTOTX_MAX_TOTAL_ETH", "2"),
            Chain.TRON: _decimal("CRYPTOTX_MAX_TOTAL_TRX", "5000"),
            Chain.BITCOIN: _decimal("CRYPTOTX_MAX_TOTAL_BTC", "0.5"),
        },
        min_gas_reserve={
            Chain.ETHEREUM: _decimal("CRYPTOTX_MIN_GAS_RESERVE_ETH", "0.002"),
            Chain.TRON: _decimal("CRYPTOTX_MIN_GAS_RESERVE_TRX", "20"),
            Chain.BITCOIN: _decimal("CRYPTOTX_MIN_GAS_RESERVE_BTC", "0.00005"),
        },
        allowed_destinations=allowed,
        require_allowlist=_flag("CRYPTOTX_REQUIRE_ALLOWLIST", False),
        request_timeout_s=float(_env("CRYPTOTX_HTTP_TIMEOUT_S", "20") or "20"),
        max_retries=int(_env("CRYPTOTX_HTTP_RETRIES", "2") or "2"),
        enabled_swap_providers=providers,
    )


def clear_config_cache() -> None:
    get_config.cache_clear()
