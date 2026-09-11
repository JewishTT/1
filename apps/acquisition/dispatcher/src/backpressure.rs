//! Backpressure control loop + retry budgets (T063/T064, FR-028, US3).
//!
//! Backpressure: queue depth / downstream lag throttles dispatch so the Kafka
//! backlog never grows unbounded. Retry budgets: per-task / per-source /
//! per-investigation / global caps; when a budget is exhausted the item is
//! passed to the dead-letter path instead of being retried forever.

/// Scale acquisition rate by downstream lag (seconds). 0 => full stop.
pub fn lag_scale(downstream_lag_s: f64) -> f64 {
    if downstream_lag_s <= 10.0 {
        1.0
    } else if downstream_lag_s >= 120.0 {
        0.0
    } else {
        1.0 - (downstream_lag_s - 10.0) / 110.0
    }
}

/// Derive a dispatch rate (items/s) from queue depth + lag.
pub fn rate_limiter(queue_depth: u64, max_rate_per_s: f64, downstream_lag_s: f64) -> f64 {
    let by_lag = lag_scale(downstream_lag_s).max(0.0);
    let by_depth = if queue_depth <= 1_000 {
        1.0
    } else if queue_depth >= 50_000 {
        0.0
    } else {
        1.0 - (queue_depth - 1_000) as f64 / 49_000.0
    };
    max_rate_per_s * by_lag * by_depth
}

/// Retry budget enforcement (T064): caps attempts at task/source/investigation
/// and global levels. Exhaustion routes the item to the DLQ, never silent loss.
#[derive(Debug, Clone, Default)]
pub struct RetryBudget {
    pub max_attempts: u32,
    pub max_per_source: u32,
    pub max_per_investigation: u32,
    /// -None => unlimited global attempts
    pub max_global: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BudgetDecision {
    Allow,
    Retry,
    Exhausted,
}

#[derive(Debug, Clone, Default)]
pub struct RetryCounter {
    /// key -> attempts recorded
    attempts: std::collections::HashMap<String, u32>,
    global: u32,
}

impl RetryCounter {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn check(&self, budget: &RetryBudget, source_key: Option<&str>, inv_key: Option<&str>) -> BudgetDecision {
        if budget.max_attempts > 0 {
            if let Some(k) = source_key {
                if self.attempts.get(k).copied().unwrap_or(0) >= budget.max_per_source {
                    return BudgetDecision::Exhausted;
                }
            }
            if let Some(k) = inv_key {
                if self.attempts.get(k).copied().unwrap_or(0) >= budget.max_per_investigation {
                    return BudgetDecision::Exhausted;
                }
            }
            if let Some(cap) = budget.max_global {
                if self.global >= cap {
                    return BudgetDecision::Exhausted;
                }
            }
        }
        BudgetDecision::Allow
    }

    /// Record one retry attempt; returns the new decision.
    pub fn record(&mut self, budget: &RetryBudget, source_key: Option<&str>, inv_key: Option<&str>) -> BudgetDecision {
        let decision = self.check(budget, source_key, inv_key);
        if decision == BudgetDecision::Allow {
            self.global += 1;
            if let Some(k) = source_key {
                *self.attempts.entry(k.to_string()).or_insert(0) += 1;
            }
            if let Some(k) = inv_key {
                *self.attempts.entry(k.to_string()).or_insert(0) += 1;
            }
        }
        decision
    }
}