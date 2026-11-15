"""Swap aggregation.

Every enabled provider that claims the pair is asked, and the best executable
quote wins. "Best" is the highest ``expected_amount_out`` after expiry filtering;
a provider that fails does not sink the route as long as another answers, and a
provider that is not configured is not asked at all. The attempts are returned
with the winner so an operator can see what was tried and why it lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from specops.cryptotx.chains.ethereum import EthereumAdapter
from specops.cryptotx.chains.registry import make_adapter
from specops.cryptotx.chains.tron import TronAdapter
from specops.cryptotx.config import CryptoTxConfig
from specops.cryptotx.errors import SwapError, SwapUnavailable
from specops.cryptotx.models import Chain, SwapQuote
from specops.cryptotx.swaps.base import SwapProvider, SwapRequest
from specops.cryptotx.swaps.evm import UniswapProvider, ZeroExProvider
from specops.cryptotx.swaps.thorchain import ThorchainProvider
from specops.cryptotx.swaps.tron import SunSwapProvider


@dataclass(frozen=True)
class SwapAttempt:
    provider: str
    quote: SwapQuote | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.quote is not None


def _expired(quote: SwapQuote) -> bool:
    if not quote.expires_at:
        return False
    try:
        moment = datetime.fromisoformat(quote.expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment <= datetime.now(UTC)


class SwapRouter:
    def __init__(
        self,
        config: CryptoTxConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport

    def _requested(self, request: SwapRequest) -> tuple[str, ...]:
        if not request.providers:
            return self.config.enabled_swap_providers
        allowed = tuple(
            name
            for name in dict.fromkeys(request.providers)
            if name in self.config.enabled_swap_providers
        )
        return allowed

    def _providers(
        self, request: SwapRequest, adapters: dict[Chain, object]
    ) -> list[SwapProvider]:
        wanted = set(self._requested(request))
        providers: list[SwapProvider] = []
        if (
            "thorchain" in wanted
            and request.from_chain is not request.to_chain
            and self.config.provider_configured("thorchain")
        ):
            providers.append(ThorchainProvider(self.config, transport=self.transport))
        if request.from_chain is Chain.ETHEREUM and request.to_chain is Chain.ETHEREUM:
            adapter = adapters.get(Chain.ETHEREUM)
            assert isinstance(adapter, EthereumAdapter)
            if "uniswap" in wanted and self.config.uniswap_router[request.network]:
                providers.append(UniswapProvider(self.config, adapter, request.network))
            if "zeroex" in wanted:
                providers.append(ZeroExProvider(self.config, transport=self.transport))
        if request.from_chain is Chain.TRON and request.to_chain is Chain.TRON:
            adapter = adapters.get(Chain.TRON)
            assert isinstance(adapter, TronAdapter)
            if "sunswap" in wanted and self.config.sunswap_router[request.network]:
                providers.append(SunSwapProvider(self.config, adapter, request.network))
        return providers

    def _adapters(self, request: SwapRequest) -> dict[Chain, object]:
        adapters: dict[Chain, object] = {}
        if request.from_chain is not request.to_chain:
            return adapters
        chain = request.from_chain
        if chain is Chain.BITCOIN:
            return adapters
        try:
            adapters[chain] = make_adapter(
                chain, request.network, config=self.config, transport=self.transport
            )
        except ValueError as exc:
            raise SwapUnavailable(str(exc)) from exc
        return adapters

    def attempts(self, request: SwapRequest) -> list[SwapAttempt]:
        adapters = self._adapters(request)
        providers = self._providers(request, adapters)
        results: list[SwapAttempt] = []
        try:
            for provider in providers:
                try:
                    if not provider.supports(request):
                        results.append(
                            SwapAttempt(provider.name, error="pair not supported")
                        )
                        continue
                    quote = provider.quote(request)
                    if _expired(quote):
                        results.append(
                            SwapAttempt(provider.name, error="quote already expired")
                        )
                        continue
                    results.append(SwapAttempt(provider.name, quote=quote))
                except (SwapUnavailable, SwapError) as exc:
                    results.append(SwapAttempt(provider.name, error=str(exc)))
                except Exception as exc:  # noqa: BLE001 - one bad provider must not stop the rest
                    results.append(
                        SwapAttempt(provider.name, error=f"{type(exc).__name__}: {exc}")
                    )
        finally:
            for provider in providers:
                close = getattr(provider, "close", None)
                if close is not None:
                    close()
            for adapter in adapters.values():
                close = getattr(adapter, "close", None)
                if close is not None:
                    close()
        return results

    def best(self, request: SwapRequest) -> tuple[SwapQuote, list[SwapAttempt]]:
        results = self.attempts(request)
        winners = [item.quote for item in results if item.quote is not None]
        if not winners:
            detail = "; ".join(
                f"{item.provider}: {item.error or 'no quote'}" for item in results
            ) or "no provider enabled for this pair"
            raise SwapUnavailable(f"no executable swap quote: {detail}")
        winners.sort(key=lambda quote: quote.expected_amount_out, reverse=True)
        return winners[0], results

    def quote(self, request: SwapRequest) -> SwapQuote:
        return self.best(request)[0]


__all__ = ["SwapAttempt", "SwapRouter"]
