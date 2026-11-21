"""Swap-provider contract.

A provider answers two questions and nothing else: can it route this pair, and
what would the route return right now? Policy, signing and broadcasting are the
executor's job. Quotes carry an expiry; a stale quote is never executed, because
the only thing worse than no swap is a swap at yesterday's price.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from specops.cryptotx.models import Asset, Chain, Network, SwapQuote


@dataclass(frozen=True)
class SwapRequest:
    from_chain: Chain
    to_chain: Chain
    network: Network
    from_asset: Asset
    to_asset: Asset
    amount: Decimal
    from_address: str
    to_address: str
    slippage_bps: int = 50
    min_amount_out: Decimal | None = None
    providers: tuple[str, ...] = ()

    def minimum_out(self, expected: Decimal) -> Decimal:
        floor = expected * (Decimal(10_000 - self.slippage_bps) / Decimal(10_000))
        if self.min_amount_out is not None:
            return max(floor, self.min_amount_out)
        return floor


class SwapProvider(ABC):
    name: str

    @abstractmethod
    def supports(self, request: SwapRequest) -> bool:
        """Whether this provider can route the pair on the requested network."""

    @abstractmethod
    def quote(self, request: SwapRequest) -> SwapQuote:
        """Return a fresh executable quote or raise ``SwapUnavailable``/``SwapError``."""
