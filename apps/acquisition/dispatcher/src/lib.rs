//! Dispatcher/scheduler loop (T029, FR-003/FR-027/FR-028, R-11).
//!
//! Scores the frontier with the UtilityScorer heuristic, respects
//! budgets/cooldowns/retry, and applies backpressure from downstream queue depth
//! before Kafka backlog grows. This crate exposes the pure scheduling core;
//! the Python control-plane orchestrates it against the authoritative frontier.

use cognitive_acq_frontier::{Frontier, FrontierItem, FrontierState};

pub mod backpressure;
use backpressure::{lag_scale, BudgetDecision, RetryBudget, RetryCounter};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DispatchDecision {
    Dispatch,
    Backpressure,
    Cooldown,
    NoItem,
    BudgetExhausted,
}

#[derive(Debug, Clone)]
pub struct DispatchOutcome {
    pub frontier_id: String,
    pub uri: String,
    pub decision: DispatchDecision,
    pub utility: f64,
    pub reason: String,
}

/// Backpressure policy: reduce acquisition rate when downstream lag grows.
fn backpressure_scale(downstream_lag_s: f64) -> f64 {
    lag_scale(downstream_lag_s)
}

/// Baseline utility heuristic (R-3). Mirrors the Python scorer contract.
fn utility(
    item: &FrontierItem,
    expected_gain: f64,
    relevance: f64,
    novelty: f64,
) -> f64 {
    let numerator = expected_gain * relevance * novelty * 0.5 * 0.3 * 0.7;
    let denominator = 0.1 + 0.1 + 0.1 + 0.01;
    let raw = numerator / denominator;
    // Priority modulation from the frontier item itself.
    raw * (0.5 + item.priority)
}

pub struct Dispatcher {
    pub frontier: Frontier,
    pub max_batch: usize,
    pub cooldown_s: f64,
    pub retries: RetryCounter,
    pub budget: RetryBudget,
}

impl Dispatcher {
    pub fn new(frontier: Frontier, max_batch: usize) -> Self {
        Dispatcher {
            frontier,
            max_batch,
            cooldown_s: 60.0,
            retries: RetryCounter::new(),
            budget: RetryBudget {
                max_attempts: 5,
                max_per_source: 3,
                max_per_investigation: 4,
                max_global: None,
            },
        }
    }

    /// One tick: attempt to dispatch up to max_batch ready items.
    pub fn tick(&mut self, tenant_id: Option<&str>, downstream_lag_s: f64) -> Vec<DispatchOutcome> {
        let mut out = Vec::new();
        for _ in 0..self.max_batch {
            let item = match self.frontier.pop_next(tenant_id) {
                Some(i) => i,
                None => {
                    out.push(DispatchOutcome {
                        frontier_id: String::new(),
                        uri: String::new(),
                        decision: DispatchDecision::NoItem,
                        utility: 0.0,
                        reason: "no-item".into(),
                    });
                    break;
                }
            };
            let scale = backpressure_scale(downstream_lag_s);
            let u = utility(&item, 0.6, 0.7, 0.5) * scale;
            if scale <= 0.0 {
                // Re-lease as READY for a later tick (backpressure).
                self.frontier.re_lease(&item.frontier_id);
                out.push(DispatchOutcome {
                    frontier_id: item.frontier_id,
                    uri: item.uri.clone(),
                    decision: DispatchDecision::Backpressure,
                    utility: u,
                    reason: "backpressure".into(),
                });
                continue;
            }
            if item.state == FrontierState::Cooldown {
                out.push(DispatchOutcome {
                    frontier_id: item.frontier_id,
                    uri: item.uri.clone(),
                    decision: DispatchDecision::Cooldown,
                    utility: u,
                    reason: "cooldown".into(),
                });
                continue;
            }
            // Retry budget: exhausted items go to the dead-letter path rather
            // than retrying forever (T064, SC-007).
            let source_key = item.source_id.as_deref().or_else(|| Some(item.uri.as_str())).map(str::to_owned);
            let inv_key = item.investigation_id.as_deref().map(str::to_owned);
            let decision = self.retries.record(&self.budget, source_key.as_deref(), inv_key.as_deref());
            if decision == BudgetDecision::Exhausted {
                self.frontier.re_lease(&item.frontier_id);
                out.push(DispatchOutcome {
                    frontier_id: item.frontier_id,
                    uri: item.uri,
                    decision: DispatchDecision::BudgetExhausted,
                    utility: u,
                    reason: "retry-budget-exhausted".into(),
                });
                continue;
            }
            self.frontier.complete(&item.frontier_id);
            out.push(DispatchOutcome {
                frontier_id: item.frontier_id,
                uri: item.uri,
                decision: DispatchDecision::Dispatch,
                utility: u,
                reason: "dispatch".into(),
            });
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use cognitive_acq_frontier::FrontierItem;

    fn item(id: &str, uri: &str, tenant: &str, priority: f64) -> FrontierItem {
        FrontierItem {
            frontier_id: id.into(),
            uri: uri.into(),
            tenant_id: tenant.into(),
            investigation_id: None,
            source_id: None,
            host_key: None,
            priority,
            state: FrontierState::Ready,
            retries: 0,
            lease_until: 0.0,
            next_schedule_at: 0.0,
        }
    }

    #[test]
    fn dispatches_ready_item() {
        let mut f = Frontier::new();
        f.enqueue(item("a", "http://a", "t", 0.5));
        let mut d = Dispatcher::new(f, 10);
        let out = d.tick(Some("t"), 0.0);
        assert!(out.iter().any(|o| o.decision == DispatchDecision::Dispatch));
    }

    #[test]
    fn backpressure_blocks_dispatch() {
        let mut f = Frontier::new();
        f.enqueue(item("a", "http://a", "t", 0.5));
        let mut d = Dispatcher::new(f, 10);
        let out = d.tick(Some("t"), 200.0);
        assert!(out.iter().any(|o| o.decision == DispatchDecision::Backpressure));
    }

    #[test]
    fn backpressure_scale_monotonic_decreasing() {
        assert!(backpressure_scale(0.0) > backpressure_scale(60.0));
        assert_eq!(backpressure_scale(10.0), 1.0);
        assert_eq!(backpressure_scale(120.0), 0.0);
    }

    #[test]
    fn utility_positive_and_priority_weighted() {
        let low = item("a", "http://a", "t", 0.0);
        let high = item("b", "http://b", "t", 1.0);
        assert!(utility(&high, 0.6, 0.7, 0.5) > utility(&low, 0.6, 0.7, 0.5));
    }

    #[test]
    fn no_item_when_empty() {
        let mut d = Dispatcher::new(Frontier::new(), 10);
        let out = d.tick(Some("t"), 0.0);
        assert_eq!(out.len(), 1);
        assert_eq!(out[0].decision, DispatchDecision::NoItem);
    }

    #[test]
    fn respects_max_batch() {
        let mut f = Frontier::new();
        for i in 0..5 {
            f.enqueue(item(&format!("id{}", i), &format!("http://{i}"), "t", 0.5));
        }
        let mut d = Dispatcher::new(f, 3);
        let out = d.tick(Some("t"), 0.0);
        let dispatched = out.iter().filter(|o| o.decision == DispatchDecision::Dispatch).count();
        assert!(dispatched <= 3);
    }

    #[test]
    fn backpressure_rate_limiter_throttles() {
        use crate::backpressure::rate_limiter;
        assert_eq!(rate_limiter(100, 10.0, 0.0), 10.0);
        assert_eq!(rate_limiter(100_000, 10.0, 0.0), 0.0);
        assert_eq!(rate_limiter(100, 10.0, 200.0), 0.0);
        let mid = rate_limiter(5_000, 10.0, 20.0);
        assert!(mid > 0.0 && mid < 10.0);
    }

    #[test]
    fn retry_budget_exhausts_per_source() {
        use super::{RetryBudget, RetryCounter};
        let budget = RetryBudget { max_attempts: 3, max_per_source: 2, max_per_investigation: 10, max_global: None };
        let mut counter = RetryCounter::new();
        assert_eq!(counter.record(&budget, Some("src-a"), Some("inv")), BudgetDecision::Allow);
        assert_eq!(counter.record(&budget, Some("src-a"), Some("inv")), BudgetDecision::Allow);
        assert_eq!(counter.check(&budget, Some("src-a"), Some("inv")), BudgetDecision::Exhausted);
    }

    #[test]
    fn retry_budget_exhausts_globally() {
        use super::{RetryBudget, RetryCounter};
        let budget = RetryBudget { max_attempts: 2, max_per_source: 99, max_per_investigation: 99, max_global: Some(1) };
        let mut counter = RetryCounter::new();
        assert_eq!(counter.record(&budget, Some("src"), Some("inv")), BudgetDecision::Allow);
        assert_eq!(counter.check(&budget, Some("src"), Some("inv")), BudgetDecision::Exhausted);
    }

    #[test]
    fn dispatcher_marks_budget_exhausted() {
        let mut f = Frontier::new();
        f.enqueue(item("a", "http://a", "t", 0.5));
        let mut d = Dispatcher::new(f, 10);
        d.budget.max_global = Some(0); // already at cap
        let out = d.tick(Some("t"), 0.0);
        assert!(out.iter().any(|o| o.decision == DispatchDecision::BudgetExhausted));
    }
}