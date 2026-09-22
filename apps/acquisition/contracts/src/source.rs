//! Source capability registry + selection (T090, T091, R-03).
//!
//! Replaces `if source == ...` routing. A source is registered with its
//! capabilities and execution class; the scheduler selects workers/adapters by
//! capability intersection. No capable engine → explicit `CapabilityGap`, never
//! a silent misroute.

use thiserror::Error;

use super::worker::{Capability, ExecutionClass};

/// Registration entry mapping a source type to its capability surface.
///
/// Adapters sit behind the untyped `adapter_ref` handle so the registry stays
/// free of `async_trait` object constraints here: the dispatcher associates the
/// registered capabilities with the concrete adapter/worker when it publishes
/// its execution classes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceRegistration {
    pub source_type: String,
    pub execution_class: ExecutionClass,
    pub capabilities: Vec<Capability>,
}

impl SourceRegistration {
    /// True when this registration covers every required capability.
    pub fn covers(&self, required: &[Capability]) -> bool {
        required.iter().all(|need| self.capabilities.contains(need))
    }

    /// Deterministic tie-break for same-class candidates (registration order).
    pub fn matches(&self, required: &[Capability]) -> bool {
        let base: &[Capability] = if required.is_empty() {
            &[Capability::new("http")]
        } else {
            required
        };
        self.covers(base)
    }
}

/// Result of a selection miss: which capabilities were missing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CapabilityGap {
    pub task_id: String,
    pub missing: Vec<Capability>,
}

impl CapabilityGap {
    pub fn new(task_id: impl Into<String>, missing: Vec<Capability>) -> Self {
        Self {
            task_id: task_id.into(),
            missing,
        }
    }
}

/// A deterministic selection outcome: either a capable registration or a gap.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Selection {
    Matched(SourceRegistration),
    Gap(CapabilityGap),
}

/// Select the first registration (declaration order) whose capability surface
/// covers the task requirements; otherwise return the missing capabilities.
/// When no requirements are declared, the conservative `http` baseline applies.
pub fn select<'a>(
    required: &'a [Capability],
    registrations: impl IntoIterator<Item = &'a SourceRegistration>,
) -> Selection {
    let owned_default;
    let base: &[Capability] = if required.is_empty() {
        owned_default = vec![Capability::new("http")];
        &owned_default
    } else {
        required
    };

    let mut missing: Vec<Capability> = base.iter().cloned().collect();
    for reg in registrations {
        if reg.covers(&base) {
            return Selection::Matched(reg.clone());
        }
        let present: Vec<Capability> = reg
            .capabilities
            .iter()
            .filter(|c| base.contains(c))
            .cloned()
            .collect();
        missing.retain(|m| !present.contains(m));
    }
    Selection::Gap(CapabilityGap {
        task_id: String::new(), // filled by caller when known
        missing,
    })
}

/// Error type for registry misuse (not a capability gap).
#[derive(Debug, Error)]
pub enum RegistryError {
    #[error("unknown execution class: {0}")]
    UnknownExecutionClass(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn reg(source: &str, class: ExecutionClass, caps: &[&str]) -> SourceRegistration {
        SourceRegistration {
            source_type: source.into(),
            execution_class: class,
            capabilities: caps.iter().map(|c| Capability::new(*c)).collect(),
        }
    }

    #[test]
    fn selects_first_capable_registration() {
        let pool = vec![
            reg("browser-baseline", ExecutionClass::Browser, &["http"]),
            reg(
                "browser-js",
                ExecutionClass::Browser,
                &["http", "javascript", "dom"],
            ),
        ];
        let req: Vec<Capability> = vec!["http".into(), "javascript".into()];
        match select(&req, pool.iter()) {
            Selection::Matched(m) => assert_eq!(m.source_type, "browser-js"),
            Selection::Gap(_) => panic!("expected match"),
        }
    }

    #[test]
    fn reports_capability_gap_with_missing_caps() {
        let pool = vec![reg("plain-http", ExecutionClass::Http, &["http"])];
        let req: Vec<Capability> = vec!["http".into(), "screenshot".into()];
        match select(&req, pool.iter()) {
            Selection::Matched(_) => panic!("expected gap"),
            Selection::Gap(g) => {
                assert!(g.missing.iter().any(|c| c.as_str() == "screenshot"));
                assert!(!g.missing.iter().any(|c| c.as_str() == "http"));
            }
        }
    }

    #[test]
    fn empty_requirements_fall_back_to_http_baseline() {
        let pool = vec![reg("plain-http", ExecutionClass::Http, &["http"])];
        match select(&[], pool.iter()) {
            Selection::Matched(m) => assert_eq!(m.source_type, "plain-http"),
            Selection::Gap(_) => panic!("http baseline must match plain-http"),
        }
    }
}