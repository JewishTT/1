//! Discovery engine (T025, FR-006, R-1).
//!
//! Parses sitemap / sitemap-index / RSS / Atom / HTML for candidate URLs.
//! Each discovery event carries method/source_id/parent_observation/timestamp.

use std::collections::HashSet;
use std::time::{SystemTime, UNIX_EPOCH};

use url::Url;

/// A discovered candidate URL with provenance metadata.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize, PartialEq)]
pub struct Discovery {
    pub url: String,
    pub method: String,        // sitemap | rss | atom | html
    pub source_id: String,
    pub parent_observation: Option<String>,
    pub timestamp_ms: u64,
    pub confidence: f32,       // 0..1
}

/// Compute a simple confidence based on how structured the discovery source is.
fn confidence(method: &str) -> f32 {
    match method {
        "sitemap" | "sitemap-index" => 0.95,
        "rss" | "atom" => 0.9,
        "html" => 0.5,
        _ => 0.3,
    }
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// Parse a sitemap or sitemap-index document for <loc> entries.
pub fn parse_sitemap(body: &str, source_id: &str, parent: Option<String>) -> Vec<Discovery> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();
    let t = now_ms();
    for loc in body.split("<loc>").skip(1) {
        if let Some(end) = loc.find("</loc>") {
            let url = loc[..end].trim().to_string();
            if !url.is_empty() && seen.insert(url.clone()) {
                out.push(Discovery {
                    url,
                    method: "sitemap".into(),
                    source_id: source_id.into(),
                    parent_observation: parent.clone(),
                    timestamp_ms: t,
                    confidence: confidence("sitemap"),
                });
            }
        }
    }
    out
}

/// Parse an RSS/Atom feed for <link> (rss item) or <link href> (atom) entries.
pub fn parse_feed(body: &str, source_id: &str, parent: Option<String>) -> Vec<Discovery> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();
    let t = now_ms();
    let method = if body.contains("<feed") { "atom" } else { "rss" };

    // Atom: <link href="..."/>
    for tok in body.split("<link") {
        if let Some(href_pos) = tok.find("href=\"") {
            let rest = &tok[href_pos + 6..];
            if let Some(end) = rest.find('"') {
                let url = rest[..end].trim().to_string();
                if !url.is_empty() && seen.insert(url.clone()) {
                    out.push(Discovery {
                        url,
                        method: method.into(),
                        source_id: source_id.into(),
                        parent_observation: parent.clone(),
                        timestamp_ms: t,
                        confidence: confidence(method),
                    });
                }
            }
        }
    }

    // RSS: <guid> or <link> (no attribute) inside <item>
    for tok in body.split("<item>").skip(1) {
        for (open, close) in [("<guid>", "</guid>"), ("<link>", "</link>")] {
            if let Some(start) = tok.find(open) {
                let rest = &tok[start + open.len()..];
                if let Some(end) = rest.find(close) {
                    let url = rest[..end].trim().to_string();
                    if !url.is_empty() && seen.insert(url.clone()) {
                        out.push(Discovery {
                            url,
                            method: method.into(),
                            source_id: source_id.into(),
                            parent_observation: parent.clone(),
                            timestamp_ms: t,
                            confidence: confidence(method),
                        });
                    }
                }
            }
        }
    }

    out
}

/// Parse raw HTML for <a href> links; dedupe, skip mailto/javascript.
pub fn parse_html_links(body: &str, source_id: &str, parent: Option<String>, base: &str) -> Vec<Discovery> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();
    let t = now_ms();
    let base_url = Url::parse(base).unwrap_or_else(|_| Url::parse("http://fixtures.local").unwrap());

    let lower = body.to_ascii_lowercase();
    for (i, _) in lower.match_indices("<a") {
        let rest = &lower[i..];
        if let Some(hi) = rest.find("href=") {
            let after = &rest[hi + 5..];
            let quote = after.chars().next();
            let url = match quote {
                Some('"') => after[1..].split('"').next().unwrap_or("").to_string(),
                Some('\'') => after[1..].split('\'').next().unwrap_or("").to_string(),
                _ => String::new(),
            };
            let trimmed = url.trim();
            if trimmed.is_empty() || trimmed.starts_with("mailto:") || trimmed.starts_with("javascript:") {
                continue;
            }
            let resolved = base_url.join(trimmed).map(|u| u.to_string()).unwrap_or_else(|_| trimmed.to_string());
            if seen.insert(resolved.clone()) {
                out.push(Discovery {
                    url: resolved,
                    method: "html".into(),
                    source_id: source_id.into(),
                    parent_observation: parent.clone(),
                    timestamp_ms: t,
                    confidence: confidence("html"),
                });
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_sitemap_locs() {
        let body = r#"<urlset><url><loc>http://a/x</loc></url><url><loc>http://a/y</loc></url></urlset>"#;
        let d = parse_sitemap(body, "src-1", Some("OBS-1".to_string()));
        assert_eq!(d.len(), 2);
        assert!(d.iter().all(|x| x.method == "sitemap" && x.confidence > 0.9));
    }

    #[test]
    fn parses_rss_items() {
        let body = r#"<rss><channel><item><guid>http://a/n1</guid></item><item><link>http://a/n2</link></item></channel></rss>"#;
        let d = parse_feed(body, "src-rss", Some("OBS-2".to_string()));
        assert!(d.iter().any(|x| x.url == "http://a/n1"));
        assert!(d.iter().any(|x| x.url == "http://a/n2"));
        assert_eq!(d[0].method, "rss");
    }

    #[test]
    fn parses_atom_links() {
        let body = r#"<feed><entry><link href="http://a/e1"/></entry></feed>"#;
        let d = parse_feed(body, "src-atom", None);
        assert!(d.iter().any(|x| x.url == "http://a/e1"));
        assert_eq!(d[0].method, "atom");
    }

    #[test]
    fn parses_html_links_and_resolves_relative() {
        let body = r#"<html><a href="/about.html">About</a><a href="http://a/abs.html">Abs</a><a href="mailto:x@y">mail</a></html>"#;
        let d = parse_html_links(body, "src-html", Some("OBS-3".to_string()), "http://fixtures.local/index.html");
        assert!(d.iter().any(|x| x.url == "http://fixtures.local/about.html"));
        assert!(d.iter().any(|x| x.url == "http://a/abs.html"));
        assert!(!d.iter().any(|x| x.url.starts_with("mailto:")));
        assert!(d.iter().all(|x| x.source_id == "src-html"));
    }

    #[test]
    fn dedupes_duplicate_urls() {
        let body = r#"<urlset><url><loc>http://a/x</loc></url><url><loc>http://a/x</loc></url></urlset>"#;
        assert_eq!(parse_sitemap(body, "s", None).len(), 1);
    }
}


