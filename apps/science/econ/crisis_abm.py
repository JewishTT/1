"""Endogenous-crisis agent-based market simulator (T070/T090).

Concept from Entropic-Dynamics-of-the-Universal-Equivalent (no license declared
→ methods only; this is a clean-room implementation, no code copied). Port of
the three-agent-class model — liquidity providers, leveraged speculators and
crisis-sensitive reallocators — with the stress/depth/spread/impact loop, plus
a reduced set of rolling diagnostics (realized variance, return entropy,
reserve-migration ratio).

   Source repo : donors/Entropic-Dynamics-of-the-Universal-Equivalent
   License     : NO-LICENSE — methods only (original implementation)
   What changed: pandas/matplotlib → numpy dataclasses; deterministic seeding;
                 crisis events surfaced; results carry a summary() contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class ABMConfig:
    """Parameter surface of the three-agent endogenous-crisis model."""
    seed: int = 42
    n_steps: int = 30000
    dt_minutes: int = 1
    initial_price: float = 1500.0
    initial_fundamental: float = 1500.0
    n_lp: int = 50
    n_spec: int = 100
    n_csr: int = 60
    base_depth: float = 8000.0
    min_depth: float = 800.0
    base_spread: float = 0.00012
    impact_scale: float = 0.000035
    fundamental_sigma: float = 0.000025
    mean_reversion: float = 0.030
    lp_inventory_limit: float = 150.0
    lp_withdraw_slope: float = 7.0
    lp_inventory_spread_weight: float = 0.00012
    lp_vol_spread_weight: float = 8.0
    spec_noise_weight: float = 3.0
    spec_trend_weight: float = 5500.0
    spec_leverage_mean: float = 1.5
    spec_leverage_std: float = 0.25
    forced_deleveraging_weight: float = 35.0
    margin_stress_threshold: float = 0.68
    csr_stress_threshold: float = 0.46
    csr_slope: float = 12.0
    csr_order_scale: float = 22.0
    stress_decay: float = 0.985
    stress_return_weight: float = 30.0
    stress_spread_weight: float = 22.0
    stress_imbalance_weight: float = 0.20
    stress_depth_weight: float = 0.30
    max_abs_return: float = 0.025
    metric_window: int = 500
    entropy_bins: int = 35


def _sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    clipped = np.clip(x, -60, 60)
    return 1.0 / (1.0 + np.exp(-clipped))


@dataclass
class CrisisABMResult:
    """Full time series of one crisis simulation (deterministic per seed)."""
    config: ABMConfig
    log_price: np.ndarray
    log_fundamental: np.ndarray
    returns: np.ndarray
    stress: np.ndarray
    spread: np.ndarray
    depth: np.ndarray
    imbalance: np.ndarray
    lp_flow: np.ndarray
    spec_flow: np.ndarray
    csr_flow: np.ndarray
    forced_deleveraging_flow: np.ndarray
    reserve_allocation: np.ndarray
    speculative_allocation: np.ndarray

    @property
    def price(self) -> np.ndarray:
        return np.exp(self.log_price)

    def crisis_events(self, *, trigger: float = 0.80) -> list[int]:
        """Indices where stress first crosses ``trigger`` (rising edge)."""
        events: list[int] = []
        crossed = False
        for t, value in enumerate(self.stress):
            if value > trigger and not crossed:
                events.append(t)
                crossed = True
            elif value <= trigger:
                crossed = False
        return events

    def summary(self) -> dict[str, Any]:
        prices = self.price
        peak = np.maximum.accumulate(prices)
        drawdown = (prices - peak) / peak
        return {
            "n_steps": len(self.stress),
            "final_price": float(prices[-1]),
            "final_stress": float(self.stress[-1]),
            "mean_return": float(np.mean(self.returns)),
            "realized_volatility": float(np.std(self.returns)),
            "max_drawdown": float(np.abs(drawdown.min())),
            "mean_spread": float(np.mean(self.spread)),
            "stress_events": len(self.crisis_events()),
            "total_forced_deleveraging": float(np.sum(np.abs(self.forced_deleveraging_flow))),
        }

    def as_dict(self) -> dict[str, Any]:
        return self.summary()

    def reserve_migration_ratio(self) -> np.ndarray:
        allocations = self.reserve_allocation + self.speculative_allocation + 1e-12
        return self.reserve_allocation / allocations


def run_abm(cfg: ABMConfig | None = None, *, seed: int | None = None) -> CrisisABMResult:
    """Run the three-agent endogenous-crisis model (deterministic given seed)."""
    config = cfg or ABMConfig()
    rng = np.random.default_rng(config.seed if seed is None else seed)

    n = config.n_steps
    log_price = np.zeros(n)
    log_fundamental = np.zeros(n)
    returns = np.zeros(n)
    spread = np.zeros(n)
    depth = np.zeros(n)
    stress = np.zeros(n)
    imbalance = np.zeros(n)
    lp_flow = np.zeros(n)
    spec_flow = np.zeros(n)
    csr_flow = np.zeros(n)
    forced_flow = np.zeros(n)
    reserve_allocation = np.zeros(n)
    speculative_allocation = np.zeros(n)

    log_price[0] = np.log(config.initial_price)
    log_fundamental[0] = np.log(config.initial_fundamental)
    spread[0] = config.base_spread
    depth[0] = config.base_depth
    stress[0] = 0.03

    lp_inventory = rng.normal(0, 4, config.n_lp)
    spec_positions = rng.normal(0, 1, config.n_spec)
    spec_leverage = np.clip(
        rng.normal(config.spec_leverage_mean, config.spec_leverage_std, config.n_spec), 0.7, 2.5
    )
    spec_sensitivity = np.clip(rng.normal(1.0, 0.25, config.n_spec), 0.4, 1.8)
    csr_thresholds = np.clip(
        rng.normal(config.csr_stress_threshold, 0.07, config.n_csr), 0.25, 0.75
    )
    csr_intensity = np.clip(rng.normal(1.0, 0.25, config.n_csr), 0.5, 1.6)

    for t in range(1, n):
        log_fundamental[t] = log_fundamental[t - 1] + rng.normal(0.0, config.fundamental_sigma)
        mispricing = log_price[t - 1] - log_fundamental[t]

        if t >= 30:
            recent = returns[t - 30 : t]
            short_vol = float(np.std(recent))
            trend = float(np.mean(recent))
        else:
            short_vol = abs(returns[t - 1])
            trend = returns[t - 1]

        prev_stress = stress[t - 1]

        active_prob = np.clip(1.0 - _sigmoid(config.lp_withdraw_slope * (prev_stress - 0.55)), 0.05, 1.0)
        lp_orders = (-15.0 * mispricing - 0.08 * lp_inventory + rng.normal(0, 1.5, config.n_lp)) * active_prob
        lp_net = float(lp_orders.sum())
        lp_inventory = np.clip(lp_inventory + 0.01 * lp_orders, -config.lp_inventory_limit, config.lp_inventory_limit)

        spec_noise = rng.normal(0, config.spec_noise_weight, config.n_spec)
        spec_trend_orders = config.spec_trend_weight * trend * spec_leverage * spec_sensitivity
        spec_orders = spec_trend_orders + spec_noise
        margin_prob = _sigmoid(14.0 * (prev_stress - config.margin_stress_threshold))
        margin_flags = rng.uniform(size=config.n_spec) < margin_prob
        deleveraging = np.zeros(config.n_spec)
        deleveraging[margin_flags] = (
            -config.forced_deleveraging_weight * np.sign(spec_positions[margin_flags] + 1e-8)
        )
        spec_orders += deleveraging
        spec_positions = np.clip(spec_positions + 0.02 * spec_orders, -80, 80)
        spec_net = float(spec_orders.sum())
        forced_net = float(deleveraging.sum())

        csr_activation = _sigmoid(config.csr_slope * (prev_stress - csr_thresholds))
        csr_orders = config.csr_order_scale * csr_intensity * csr_activation + rng.normal(0, 1.2, config.n_csr)
        csr_net = float(csr_orders.sum())

        total_order = lp_net + spec_net + csr_net
        gross_flow = abs(lp_net) + abs(spec_net) + abs(csr_net) + 1e-8
        imb = total_order / gross_flow

        depth_t = (
            config.base_depth
            * (1.0 - 0.55 * min(prev_stress, 1.0))
            * np.exp(-6.0 * short_vol)
            * (0.65 + 0.35 * active_prob)
        )
        depth_t = float(np.clip(depth_t, config.min_depth, config.base_depth))
        inv_pressure = float(np.mean(np.abs(lp_inventory))) / config.lp_inventory_limit
        spread_t = float(
            np.clip(
                config.base_spread
                + config.lp_vol_spread_weight * short_vol
                + config.lp_inventory_spread_weight * inv_pressure
                + 0.0015 * (1.0 - active_prob),
                config.base_spread,
                0.025,
            )
        )

        impact = config.impact_scale * total_order / depth_t
        reversion = -config.mean_reversion * mispricing
        noise = rng.normal(0, 0.00008 + 0.15 * short_vol)
        jump_prob = float(_sigmoid(10.0 * (prev_stress - 0.75)) * min(1.0, 2.5 * abs(imb)))
        jump = 0.0
        if rng.uniform() < jump_prob:
            jump = rng.normal(0, 0.0025 + 1.5 * short_vol)
        r_t = float(np.clip(reversion + impact + noise + jump, -config.max_abs_return, config.max_abs_return))

        returns[t] = r_t
        log_price[t] = log_price[t - 1] + r_t

        stress_innovation = (
            config.stress_return_weight * abs(r_t)
            + config.stress_spread_weight * spread_t
            + config.stress_imbalance_weight * abs(imb)
            + config.stress_depth_weight * (1.0 - depth_t / config.base_depth)
        )
        stress[t] = np.clip(
            config.stress_decay * prev_stress + (1.0 - config.stress_decay) * stress_innovation,
            0.0,
            1.0,
        )

        reserve_allocation[t] = (
            abs(csr_net) + 0.50 * max(lp_net, 0.0) + 0.10 * depth_t / config.base_depth
        )
        speculative_allocation[t] = abs(spec_net) + abs(forced_net) + 0.10 * abs(imb)

        spread[t] = spread_t
        depth[t] = depth_t
        imbalance[t] = imb
        lp_flow[t] = lp_net
        spec_flow[t] = spec_net
        csr_flow[t] = csr_net
        forced_flow[t] = forced_net

    return CrisisABMResult(
        config=config,
        log_price=log_price,
        log_fundamental=log_fundamental,
        returns=returns,
        stress=stress,
        spread=spread,
        depth=depth,
        imbalance=imbalance,
        lp_flow=lp_flow,
        spec_flow=spec_flow,
        csr_flow=csr_flow,
        forced_deleveraging_flow=forced_flow,
        reserve_allocation=reserve_allocation,
        speculative_allocation=speculative_allocation,
    )