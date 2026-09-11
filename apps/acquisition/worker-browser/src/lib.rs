//! Browser fabric escalation path (T067, US3).
//!
//! The browser worker pool is isolated from all other worker pools and used
//! ONLY on escalation: when a URI cannot be satisfied by the cheap fabric
//! (HTTP/browser-less), the dispatcher routes the item here. The pool refuses
//! any non-escalated feed and never shares capacity with other workers, so a
//! browser failure cannot stall acquisition.

/// Why a URI needs the browser fabric (escalation trigger).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EscalationReason {
    ClientRendered,
    AntiBotChallenge,
    RequiresHeadful,
    LoginWall,
}

impl EscalationReason {
    pub fn as_str(self) -> &'static str {
        match self {
            EscalationReason::ClientRendered => "client-rendered",
            EscalationReason::AntiBotChallenge => "anti-bot-challenge",
            EscalationReason::RequiresHeadful => "requires-headful",
            EscalationReason::LoginWall => "login-wall",
        }
    }
}

/// A work item that may enter the browser pool.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BrowserTask {
    pub task_id: String,
    pub uri: String,
    pub escalation: bool,
    pub reason: Option<EscalationReason>,
}

/// Admission gate for the browser pool.
pub fn admit(task: &BrowserTask) -> Result<(), BrowserAdmissionError> {
    if !task.escalation {
        return Err(BrowserAdmissionError::NotEscalated(task.uri.clone()));
    }
    if task.reason.is_none() {
        return Err(BrowserAdmissionError::MissingReason(task.uri.clone()));
    }
    if task.uri.starts_with("http://") || task.uri.starts_with("https://") {
        Ok(())
    } else {
        Err(BrowserAdmissionError::NotHttp(task.uri.clone()))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BrowserAdmissionError {
    NotEscalated(String),
    MissingReason(String),
    NotHttp(String),
}

impl std::fmt::Display for BrowserAdmissionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BrowserAdmissionError::NotEscalated(u) => write!(f, "browser pool refused non-escalated feed: {u}"),
            BrowserAdmissionError::MissingReason(u) => write!(f, "browser pool requires an escalation reason: {u}"),
            BrowserAdmissionError::NotHttp(u) => write!(f, "browser pool only accepts http(s) URIs: {u}"),
        }
    }
}

/// Fixed-capacity concurrency guard so the browser pool cannot starve others.
#[derive(Debug)]
pub struct BrowserPool {
    pub name: String,
    pub capacity: usize,
    active: std::sync::atomic::AtomicUsize,
    slots: std::sync::atomic::AtomicUsize,
}

impl BrowserPool {
    pub fn new(name: &str, capacity: usize) -> Self {
        BrowserPool {
            name: name.to_string(),
            capacity,
            active: std::sync::atomic::AtomicUsize::new(0),
            slots: std::sync::atomic::AtomicUsize::new(capacity),
        }
    }

    pub fn available(&self) -> usize {
        self.slots.load(std::sync::atomic::Ordering::SeqCst)
    }

    /// Try to book a slot. Returns None when the pool is saturated.
    pub fn try_acquire(&self) -> Option<PoolSlot<'_>> {
        loop {
            let cur = self.slots.load(std::sync::atomic::Ordering::SeqCst);
            if cur == 0 {
                return None;
            }
            if self
                .slots
                .compare_exchange_weak(cur, cur - 1, std::sync::atomic::Ordering::SeqCst, std::sync::atomic::Ordering::SeqCst)
                .is_ok()
            {
                self.active.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                return Some(PoolSlot { pool: self });
            }
        }
    }
}

#[derive(Debug)]
pub struct PoolSlot<'a> {
    pool: &'a BrowserPool,
}

impl Drop for PoolSlot<'_> {
    fn drop(&mut self) {
        self.pool.slots.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        self.pool.active.fetch_sub(1, std::sync::atomic::Ordering::SeqCst);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn task(id: &str, uri: &str, escalation: bool, reason: Option<EscalationReason>) -> BrowserTask {
        BrowserTask { task_id: id.into(), uri: uri.into(), escalation, reason }
    }

    #[test]
    fn refuses_non_escalated_feed() {
        assert!(admit(&task("t1", "http://x", false, Some(EscalationReason::ClientRendered))).is_err());
    }

    #[test]
    fn refuses_escalation_without_reason() {
        assert!(admit(&task("t2", "http://x", true, None)).is_err());
    }

    #[test]
    fn admits_escalated_http_task() {
        assert_eq!(admit(&task("t3", "http://x", true, Some(EscalationReason::AntiBotChallenge))), Ok(()));
    }

    #[test]
    fn refuses_non_http() {
        assert!(admit(&task("t4", "ftp://x", true, Some(EscalationReason::LoginWall))).is_err());
    }

    #[test]
    fn pool_isolated_capacity() {
        let pool = BrowserPool::new("browser", 2);
        let a = pool.try_acquire();
        let b = pool.try_acquire();
        assert!(a.is_some() && b.is_some());
        assert!(pool.try_acquire().is_none()); // saturated, others unaffected
        assert_eq!(pool.available(), 0);
        drop(a);
        assert_eq!(pool.available(), 1);
    }

    #[test]
    fn browsers_are_segregated_pools() {
        let browser = BrowserPool::new("browser", 1);
        let http = BrowserPool::new("http", 3);
        let _b = browser.try_acquire();
        // HTTP pool never blocks even when browser is saturated.
        assert_eq!(http.available(), 3);
    }
}