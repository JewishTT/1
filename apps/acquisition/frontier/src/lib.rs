//! Frontier operational state (T026, FR-003, R-4).
//!
//! Postgres is authoritative (hierarchical GLOBAL→TENANT→INVESTIGATION→SOURCE→
//! HOST→TASK); Redis provides hot lease/cooldown/locking. Kafka is never the
//! frontier queue (I-5/R-4). This crate exposes the in-memory frontier with
//! lease/cooldown/retry semantics; a Postgres/Redis-backed implementation is a
//! drop-in behind the same trait.

use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq)]
pub enum FrontierState {
    Ready,
    Leased,
    Done,
    Cooldown,
    Retry,
    Quarantined,
}

#[derive(Debug, Clone)]
pub struct FrontierItem {
    pub frontier_id: String,
    pub uri: String,
    pub tenant_id: String,
    pub investigation_id: Option<String>,
    pub source_id: Option<String>,
    pub host_key: Option<String>,
    pub priority: f64,
    pub state: FrontierState,
    pub retries: u32,
    pub lease_until: f64,
    pub next_schedule_at: f64,
}

impl FrontierItem {
    fn schedule_key(&self) -> String {
        format!("{}:{}", self.tenant_id, self.uri)
    }
}

fn now_ms() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64() * 1000.0)
        .unwrap_or(0.0)
}

pub struct Frontier {
    items: HashMap<String, FrontierItem>,
    by_schedule: HashMap<String, String>,
}

impl Default for Frontier {
    fn default() -> Self {
        Self::new()
    }
}

impl Frontier {
    pub fn new() -> Self {
        Frontier { items: HashMap::new(), by_schedule: HashMap::new() }
    }

    pub fn enqueue(&mut self, item: FrontierItem) -> bool {
        let key = item.schedule_key();
        if let Some(existing_id) = self.by_schedule.get(&key).map(|s| s.clone()) {
            let existing = self.items.get_mut(&existing_id).unwrap();
            if item.priority > existing.priority {
                existing.priority = item.priority;
                existing.state = FrontierState::Ready;
            }
            return false;
        }
        self.by_schedule.insert(key, item.frontier_id.clone());
        self.items.insert(item.frontier_id.clone(), item);
        true
    }

    pub fn pop_next(&mut self, tenant_id: Option<&str>) -> Option<FrontierItem> {
        let now = now_ms();
        let mut best: Option<(String, f64)> = None;
        for (id, it) in &self.items {
            let eligible = matches!(it.state, FrontierState::Ready | FrontierState::Retry);
            let tenant_ok = tenant_id.map_or(true, |t| it.tenant_id == t);
            if eligible && tenant_ok && it.next_schedule_at <= now {
                if best.as_ref().map_or(true, |(_, p)| it.priority > *p) {
                    best = Some((id.clone(), it.priority));
                }
            }
        }
        if let Some((id, _)) = best {
            let item = self.items.get_mut(&id).unwrap();
            item.state = FrontierState::Leased;
            item.lease_until = now + 30_000.0;
            return Some(item.clone());
        }
        None
    }

    pub fn complete(&mut self, frontier_id: &str) {
        if let Some(it) = self.items.get_mut(frontier_id) {
            it.state = FrontierState::Done;
            it.next_schedule_at = now_ms() + 3_600_000.0;
        }
    }

    /// Re-lease an item back to READY (e.g. when backpressure suspends dispatch).
    pub fn re_lease(&mut self, frontier_id: &str) {
        if let Some(it) = self.items.get_mut(frontier_id) {
            it.state = FrontierState::Ready;
            it.lease_until = 0.0;
        }
    }

    pub fn fail_retry(&mut self, frontier_id: &str, max_retries: u32, cooldown_s: f64) {
        if let Some(it) = self.items.get_mut(frontier_id) {
            if it.retries >= max_retries {
                it.state = FrontierState::Quarantined;
                return;
            }
            it.retries += 1;
            it.state = FrontierState::Retry;
            it.next_schedule_at = now_ms() + cooldown_s * 1000.0;
        }
    }

    pub fn count(&self) -> usize {
        self.items.len()
    }

    pub fn ready_count(&self) -> usize {
        self.items
            .values()
            .filter(|i| matches!(i.state, FrontierState::Ready | FrontierState::Retry))
            .count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
    fn enqueue_dedupes_duplicate_uri() {
        let mut f = Frontier::new();
        assert!(f.enqueue(item("a", "http://x", "t", 0.5)));
        assert!(!f.enqueue(item("b", "http://x", "t", 0.6)));
        assert_eq!(f.count(), 1);
    }

    #[test]
    fn enqueue_upgrades_priority_on_duplicate() {
        let mut f = Frontier::new();
        f.enqueue(item("a", "http://x", "t", 0.5));
        f.enqueue(item("b", "http://x", "t", 0.9));
        let popped = f.pop_next(Some("t")).unwrap();
        assert_eq!(popped.priority, 0.9);
    }

    #[test]
    fn pop_next_returns_highest_priority_ready() {
        let mut f = Frontier::new();
        f.enqueue(item("a", "http://a", "t", 0.3));
        f.enqueue(item("b", "http://b", "t", 0.9));
        let popped = f.pop_next(Some("t")).unwrap();
        assert_eq!(popped.frontier_id, "b");
        assert_eq!(popped.state, FrontierState::Leased);
    }

    #[test]
    fn pop_next_respects_tenant_isolation() {
        let mut f = Frontier::new();
        f.enqueue(item("a", "http://a", "t1", 0.9));
        f.enqueue(item("b", "http://b", "t2", 0.9));
        assert!(f.pop_next(Some("t1")).is_some());
        assert_eq!(f.ready_count(), 1);
    }

    #[test]
    fn fail_retry_quarantines_after_max() {
        let mut f = Frontier::new();
        f.enqueue(item("a", "http://a", "t", 0.5));
        for _ in 0..4 {
            f.fail_retry("a", 3, 60.0);
        }
        let it = f.items.get("a").unwrap();
        assert_eq!(it.state, FrontierState::Quarantined);
    }

    #[test]
    fn complete_marks_done_and_reschedules() {
        let mut f = Frontier::new();
        f.enqueue(item("a", "http://a", "t", 0.5));
        f.complete("a");
        let it = f.items.get("a").unwrap();
        assert_eq!(it.state, FrontierState::Done);
        assert!(it.next_schedule_at > now_ms());
    }
}