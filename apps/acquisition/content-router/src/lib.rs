//! Content Router — what downstream work an observation drives (T042, R-08).
//!
//! The gate decides lifecycle (`created/changed/unchanged/duplicate`); the router
//! decides *what happens next* based on the bytes' nature. It classifies each
//! observation into a [`ContentKind`] (from declared MIME + magic-byte sniffing)
//! and emits a [`Route`]:
//!
//! - `Extract`  → HTML/text: link discovery + full-text projection
//! - `Archive`  → media/binaries: preserve bytes only
//! - `Dataset`  → structured payloads: analytical namespace (lakehouse)
//! - `Feed`     → RSS/Atom: subscription refresh / cadence control
//! - `NoOp`     → duplicate/unchanged: no re-ingestion (dedup split)
//! - `Review`   → unknown: quarantine for a human/decision
//!
//! The router is independent (no gate/contract deps) so any projection consumer
//! can classify bytes uniformly. MIME is a hint; magic bytes win on conflict.

/// High-level nature of the content after MIME normalization + sniffing.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContentKind {
    Html,
    Feed,
    Json,
    Text,
    Document,
    Image,
    Audio,
    Video,
    Warc,
    Dataset,
    Binary,
    Unknown,
}

impl ContentKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Html => "html",
            Self::Feed => "feed",
            Self::Json => "json",
            Self::Text => "text",
            Self::Document => "document",
            Self::Image => "image",
            Self::Audio => "audio",
            Self::Video => "video",
            Self::Warc => "warc",
            Self::Dataset => "dataset",
            Self::Binary => "binary",
            Self::Unknown => "unknown",
        }
    }
}

impl std::fmt::Display for ContentKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Downstream route for one observation. `NoOp` carries the dedup split: when
/// the gate reports `duplicate`/`unchanged` nothing downstream re-runs.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Route {
    Extract,
    Archive,
    Dataset,
    Feed,
    NoOp,
    Review,
}

impl Route {
    /// True when the observation warrants a new projection pass.
    pub fn is_actionable(self) -> bool {
        !matches!(self, Self::NoOp)
    }
}

/// Classified observation: normalized MIME + the derived kind/handlers.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContentClass {
    /// Parameters stripped, lowercased ("text/html; charset=utf-8" -> "text/html").
    pub mime: Option<String>,
    pub kind: ContentKind,
    /// Textual payload → full-text projection candidates.
    pub textual: bool,
    /// Bytes preserved verbatim (media/binary/WARC) vs. decoded.
    pub archive_as_is: bool,
}

/// Default router with the built-in sniffing table.
#[derive(Debug, Default)]
pub struct Router;

impl Router {
    pub fn new() -> Self {
        Self
    }

    /// Combine MIME hint + optional magic-byte sniffing into a class.
    /// Sniffing only happens when a sample is provided; it overrides a generic
    /// `application/octet-stream` and confirms ambiguous text containers.
    pub fn classify(&self, mime: Option<&str>, sample: Option<&[u8]>) -> ContentClass {
        let mime = mime.map(normalize_mime);
        let mut kind = kind_from_mime(mime.as_deref());
        if let Some(bytes) = sample {
            if kind == ContentKind::Unknown
                || kind == ContentKind::Binary
                || kind == ContentKind::Text
            {
                let sniffed = kind_from_magic(bytes);
                if sniffed != ContentKind::Unknown && sniffed != kind {
                    kind = sniffed;
                }
            }
        }
        let (textual, archive_as_is) = match kind {
            ContentKind::Html
            | ContentKind::Feed
            | ContentKind::Json
            | ContentKind::Text => (true, false),
            ContentKind::Document => (true, false),
            ContentKind::Image
            | ContentKind::Audio
            | ContentKind::Video
            | ContentKind::Warc
            | ContentKind::Dataset
            | ContentKind::Binary => (false, true),
            ContentKind::Unknown => (false, false),
        };
        ContentClass { mime, kind, textual, archive_as_is }
    }

    /// Full routing: kind → downstream pipeline.
    pub fn route(&self, mime: Option<&str>, sample: Option<&[u8]>) -> Route {
        match self.classify(mime, sample).kind {
            ContentKind::Html => Route::Extract,
            ContentKind::Json | ContentKind::Document | ContentKind::Text => Route::Extract,
            ContentKind::Feed => Route::Feed,
            ContentKind::Dataset => Route::Dataset,
            ContentKind::Image | ContentKind::Audio | ContentKind::Video | ContentKind::Warc | ContentKind::Binary => Route::Archive,
            ContentKind::Unknown => Route::Review,
        }
    }

    /// Lifecycle-aware routing (R-08 three-way split): `duplicate`/`unchanged`
    /// short-circuit to `NoOp`, fresh content routes normally.
    pub fn route_lifecycle(&self, is_fresh: bool, mime: Option<&str>, sample: Option<&[u8]>) -> Route {
        if !is_fresh {
            return Route::NoOp;
        }
        self.route(mime, sample)
    }
}

/// Strip parameters, lowercase ("TEXT/HTML; charset=utf-8" -> "text/html").
pub fn normalize_mime(raw: &str) -> String {
    let base = raw.split(';').next().unwrap_or("").trim().to_ascii_lowercase();
    base
}

/// Magic-byte sniffing for common web payloads. Returns `Unknown` when no
/// signature matches; gzip payloads (e.g. WARC.gz) are surfaced so the caller
/// can decide (the header sample below a gzip stream is opaque).
pub fn kind_from_magic(bytes: &[u8]) -> ContentKind {
    if bytes.is_empty() {
        return ContentKind::Unknown;
    }
    // Skip UTF-8 BOM (EF BB BF) before text detection.
    let body = if bytes.starts_with(&[0xEF, 0xBB, 0xBF]) { &bytes[3..] } else { bytes };

    if body.starts_with(&[0x1F, 0x8B]) {
        return ContentKind::Binary; // gzip: caller must decompress to inspect
    }
    if body.starts_with(b"%PDF-") {
        return ContentKind::Document;
    }
    if body.starts_with(&[0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A]) {
        return ContentKind::Image;
    }
    if body.len() >= 3 && body[0] == 0xFF && body[1] == 0xD8 && body[2] == 0xFF {
        return ContentKind::Image;
    }
    if body.starts_with(b"GIF87a") || body.starts_with(b"GIF89a") {
        return ContentKind::Image;
    }
    if body.len() >= 12 && &body[0..4] == b"RIFF" && &body[8..12] == b"WEBP" {
        return ContentKind::Image;
    }
    // ftyp box: avif (avif/avis), mif1 (heic), mp4 is handled by video sniff below.
    if body.len() >= 12 && &body[4..8] == b"ftyp" && body[8..12].starts_with(b"avif") {
        return ContentKind::Image;
    }
    if body.len() >= 12 && &body[4..8] == b"ftyp" {
        let brand = &body[8..12];
        if brand == b"isom" || brand == b"mp41" || brand == b"mp42" || brand == b"avc1"
            || brand == b"qt  " || brand == b"m4v " || brand == b"mp4v"
        {
            return ContentKind::Video;
        }
        return ContentKind::Video;
    }
    if body.starts_with(b"PK\x03\x04") {
        // ZIP containers: EPUB/DOCX (documents) vs. generic zips (datasets).
        // Without a manifest walk we conservatively classify as Binary; callers
        // with a filename hint upgrade via MIME.
        return ContentKind::Binary;
    }
    if body.len() > 262 && &body[257..262] == b"ustar" {
        return ContentKind::Dataset; // tarball: bulk dataset
    }
    if body.starts_with(b"PAR1") {
        return ContentKind::Dataset;
    }
    if body.starts_with(b"WARC/") || body.starts_with(b"WARC-") {
        return ContentKind::Warc;
    }
    if body.starts_with(b"<!DOCTYPE html") || body.starts_with(b"<!doctype html")
        || body.starts_with(b"<html") || body.starts_with(b"<HTML")
    {
        return ContentKind::Html;
    }
    if body.starts_with(b"<?xml") || body.starts_with(b"<feed") || body.starts_with(b"<rss")
    {
        // XML container: distinguishing feed from generic XML needs a peek at
        // the root; check for feed roots first (handled below), else Text.
        if contains_feed_root(body) {
            return ContentKind::Feed;
        }
        return ContentKind::Text;
    }
    if body.starts_with(b"{") || body.starts_with(b"[") {
        return ContentKind::Json;
    }
    if body.starts_with(b"<svg") || body.starts_with(b"<SVG") {
        return ContentKind::Image;
    }
    ContentKind::Unknown
}

/// Rudimentary root-element sniff for RSS/Atom feeds inside an XML document.
fn contains_feed_root(body: &[u8]) -> bool {
    let text = String::from_utf8_lossy(&body[..body.len().min(2048)]);
    let t = text.trim_start();
    t.starts_with("<rss") || t.starts_with("<feed") || t.contains("<channel")
}

/// MIME → kind when the hint is authoritative.
fn kind_from_mime(mime: Option<&str>) -> ContentKind {
    match mime {
        None => ContentKind::Unknown,
        Some("text/html") | Some("application/xhtml+xml") => ContentKind::Html,
        Some("application/rss+xml") | Some("application/atom+xml") | Some("application/xml")
        | Some("text/xml") => ContentKind::Feed,
        Some("application/json") | Some("application/ld+json") | Some("application/x-ndjson")
        | Some("text/json") => ContentKind::Json,
        Some("application/pdf") | Some("application/epub+zip") | Some("application/msword")
        | Some("application/vnd.openxmlformats-officedocument.wordprocessingml.document") => {
            ContentKind::Document
        }
        Some("image/png") | Some("image/jpeg") | Some("image/gif") | Some("image/webp")
        | Some("image/avif") | Some("image/svg+xml") | Some("image/x-icon") => ContentKind::Image,
        Some("audio/mpeg") | Some("audio/mp4") | Some("audio/ogg") | Some("audio/wav")
        | Some("audio/x-wav") | Some("audio/flac") => ContentKind::Audio,
        Some("video/mp4") | Some("video/webm") | Some("video/ogg") | Some("video/x-matroska")
        | Some("video/quicktime") => ContentKind::Video,
        Some("application/warc") | Some("application/x-warc") | Some("application/webarchive")
        | Some("application/vnd.tcpdump.pcap") => ContentKind::Warc,
        Some("application/vnd.apache.parquet") | Some("application/parquet")
        | Some("application/x-parquet") => ContentKind::Dataset,
        Some("application/octet-stream") | Some("application/binary") => ContentKind::Binary,
        Some("text/plain") | Some("text/markdown") | Some("text/csv")
        | Some("application/csv") | Some("text/css") | Some("text/javascript")
        | Some("application/javascript") => ContentKind::Text,
        Some(_) => ContentKind::Unknown,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mime_normalization_strips_params_and_lowercases() {
        assert_eq!(normalize_mime("TEXT/HTML; charset=utf-8"), "text/html");
        assert_eq!(normalize_mime("application/JSON"), "application/json");
    }

    #[test]
    fn routes_html_to_extract() {
        let r = Router::new();
        assert_eq!(
            r.route(Some("text/html"), Some(b"<html><body>hi</body></html>")),
            Route::Extract
        );
    }

    #[test]
    fn feeds_route_to_feed_not_extract() {
        let r = Router::new();
        assert_eq!(
            r.route(Some("application/rss+xml"), None),
            Route::Feed
        );
        let xml = br#"<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>"#;
        assert_eq!(r.route(None, Some(xml)), Route::Feed);
    }

    #[test]
    fn pdf_magic_beats_missing_mime() {
        let r = Router::new();
        assert_eq!(r.route(None, Some(b"%PDF-1.7\n%%EOF")), Route::Extract);
        assert_eq!(r.classify(None, Some(b"%PDF-1.7")).kind, ContentKind::Document);
    }

    #[test]
    fn png_magic_detects_image() {
        let png: [u8; 8] = [0x89, b'P', b'N', b'G', 0x0D, 0x0A, 0x1A, 0x0A];
        let r = Router::new();
        assert_eq!(r.route(None, Some(&png)), Route::Archive);
        assert_eq!(r.classify(None, Some(&png)).archive_as_is, true);
        assert_eq!(r.classify(None, Some(&png)).textual, false);
    }

    #[test]
    fn json_octet_stream_is_promoted_by_sniffing() {
        let r = Router::new();
        let body = br#"{"tenant_id":"t-1","count":3}"#;
        // Generic MIME hint is upgraded by the leading '{'.
        let class = r.classify(Some("application/octet-stream"), Some(body));
        assert_eq!(class.kind, ContentKind::Json);
        assert_eq!(r.route(Some("application/octet-stream"), Some(body)), Route::Extract);
    }

    #[test]
    fn warc_magic_is_archival() {
        let data = b"WARC/1.1\r\nWARC-Type: warcinfo\r\n\r\n";
        let r = Router::new();
        let class = r.classify(Some("application/warc"), Some(data));
        assert_eq!(class.kind, ContentKind::Warc);
        assert_eq!(class.archive_as_is, true);
        assert_eq!(r.route(Some("application/warc"), Some(data)), Route::Archive);
        // gzip-wrapped WARC: container is opaque, but MIME wakes the kind.
        let gz = [0x1F, 0x8B, 0x08, 0x00];
        assert_eq!(r.classify(Some("application/warc"), Some(&gz)).kind, ContentKind::Warc);
    }

    #[test]
    fn parquet_magic_is_dataset() {
        let r = Router::new();
        assert_eq!(r.route(None, Some(b"PAR1....")), Route::Dataset);
    }

    #[test]
    fn unknown_routes_to_review() {
        let r = Router::new();
        assert_eq!(r.route(None, Some(b"\x00\x01\x02\x03\x04")), Route::Review);
        assert_eq!(r.route(Some("application/octet-stream"), Some(b"\x00\x01")), Route::Archive);
    }

    #[test]
    fn duplicate_and_unchanged_short_circuit_to_noop() {
        let r = Router::new();
        assert_eq!(r.route_lifecycle(false, Some("text/html"), Some(b"<html>")), Route::NoOp);
        assert_eq!(r.route_lifecycle(true, Some("text/html"), Some(b"<html>")), Route::Extract);
    }

    #[test]
    fn bom_utf8_html_still_detected() {
        let mut bytes = vec![0xEF, 0xBB, 0xBF];
        bytes.extend_from_slice(b"<!DOCTYPE html><html></html>");
        let r = Router::new();
        assert_eq!(r.classify(None, Some(&bytes)).kind, ContentKind::Html);
    }

    #[test]
    fn gzip_stream_is_binary_not_unknown() {
        let r = Router::new();
        let gz = [0x1F, 0x8B, 0x08, 0x00];
        assert_eq!(r.classify(None, Some(&gz)).kind, ContentKind::Binary);
    }
}