use proc_macro2::Span;
use quote::ToTokens;
use serde_json::{json, Value};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use syn::{spanned::Spanned, visit::Visit, Attribute, ExprCall, ExprMethodCall, Item, Visibility};

const ROOTS: &[&str] = &["apps", "bench", "benchmarks", "tools", "platform_model", "implementation", "specs"];
const EXCLUDED: &[&str] = &[
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".ruff_cache", "target", "dist", "build", "tmp", "logs", "donors",
];

fn line(span: Span) -> usize {
    span.start().line
}

fn docs(attrs: &[Attribute]) -> String {
    attrs.iter().filter_map(|attr| {
        if !attr.path().is_ident("doc") { return None; }
        match &attr.meta {
            syn::Meta::NameValue(value) => match &value.value {
                syn::Expr::Lit(lit) => match &lit.lit {
                    syn::Lit::Str(text) => Some(text.value().trim().to_string()),
                    _ => None,
                },
                _ => None,
            },
            _ => None,
        }
    }).collect::<Vec<_>>().join(" ").trim().chars().take(240).collect()
}

fn is_public(visibility: &Visibility) -> bool {
    matches!(visibility, Visibility::Public(_))
}

fn push_symbol(out: &mut Vec<Value>, path: &str, name: String, kind: &str, public: bool,
               row: usize, doc: String, signature: String) {
    out.push(json!({
        "name": name, "qualified_name": name, "kind": kind, "public": public,
        "line": row, "docstring": doc, "signature": signature
    }));
}

fn scan_items(items: &[Item], out: &mut Vec<Value>, imports: &mut Vec<Value>, routes: &mut Vec<Value>) {
    for item in items {
        match item {
            Item::Fn(value) => {
                push_symbol(out, "", value.sig.ident.to_string(), "function", is_public(&value.vis),
                    line(value.span()), docs(&value.attrs), value.sig.to_token_stream().to_string());
            }
            Item::Struct(value) => push_symbol(out, "", value.ident.to_string(), "struct",
                is_public(&value.vis), line(value.span()), docs(&value.attrs), value.to_token_stream().to_string()),
            Item::Enum(value) => push_symbol(out, "", value.ident.to_string(), "enum",
                is_public(&value.vis), line(value.span()), docs(&value.attrs), value.to_token_stream().to_string()),
            Item::Trait(value) => push_symbol(out, "", value.ident.to_string(), "trait",
                is_public(&value.vis), line(value.span()), docs(&value.attrs), value.to_token_stream().to_string()),
            Item::Type(value) => push_symbol(out, "", value.ident.to_string(), "type",
                is_public(&value.vis), line(value.span()), docs(&value.attrs), value.to_token_stream().to_string()),
            Item::Const(value) => push_symbol(out, "", value.ident.to_string(), "constant",
                is_public(&value.vis), line(value.span()), docs(&value.attrs), value.to_token_stream().to_string()),
            Item::Static(value) => push_symbol(out, "", value.ident.to_string(), "static",
                is_public(&value.vis), line(value.span()), docs(&value.attrs), value.to_token_stream().to_string()),
            Item::Mod(value) => {
                push_symbol(out, "", value.ident.to_string(), "module", is_public(&value.vis),
                    line(value.span()), docs(&value.attrs), value.to_token_stream().to_string());
                if let Some((_, children)) = &value.content {
                    scan_items(children, out, imports, routes);
                }
            }
            Item::Impl(value) => {
                let subject = value.self_ty.to_token_stream().to_string();
                push_symbol(out, "", "impl " .to_string() + &subject, "impl", true,
                    line(value.span()), docs(&value.attrs), value.to_token_stream().to_string());
                for child in &value.items {
                    if let syn::ImplItem::Fn(method) = child {
                        push_symbol(out, "", subject.clone() + "::" + &method.sig.ident.to_string(),
                            "method", is_public(&method.vis), line(method.span()), docs(&method.attrs),
                            method.sig.to_token_stream().to_string());
                    }
                }
            }
            Item::Use(value) => imports.push(json!({
                "module": value.tree.to_token_stream().to_string(),
                "specifier": value.tree.to_token_stream().to_string(),
                "line": line(value.span()), "kind": "use"
            })),
            _ => {}
        }
    }
}

fn walk(root: &Path, dir: &Path, files: &mut Vec<PathBuf>) {
    let entries = match fs::read_dir(dir) { Ok(v) => v, Err(_) => return };
    let mut entries: Vec<_> = entries.filter_map(Result::ok).collect();
    entries.sort_by_key(|entry| entry.file_name());
    for entry in entries {
        let path = entry.path();
        if path.is_dir() {
            let name = entry.file_name().to_string_lossy().to_string();
            if !EXCLUDED.contains(&name.as_str()) { walk(root, &path, files); }
        } else if path.extension().is_some_and(|ext| ext == "rs") {
            files.push(path);
        }
    }
}

#[derive(Default)]
struct CallCollector {
    calls: Vec<Value>,
}
impl<'ast> Visit<'ast> for CallCollector {
    fn visit_expr_call(&mut self, node: &'ast ExprCall) {
        self.calls.push(json!({
            "callee": node.func.to_token_stream().to_string(),
            "line": line(node.span())
        }));
        syn::visit::visit_expr_call(self, node);
    }
    fn visit_expr_method_call(&mut self, node: &'ast ExprMethodCall) {
        self.calls.push(json!({
            "callee": node.method.to_string(),
            "line": line(node.span())
        }));
        syn::visit::visit_expr_method_call(self, node);
    }
}

fn main() {
    let mut args = env::args().skip(1);
    let mut root = PathBuf::from(".");
    while let Some(arg) = args.next() {
        if arg == "--root" {
            if let Some(value) = args.next() { root = PathBuf::from(value); }
        }
    }
    let root = root.canonicalize().unwrap_or(root);
    let mut files = Vec::new();
    for base in ROOTS { walk(&root, &root.join(base), &mut files); }
    if let Ok(entries) = fs::read_dir(&root) {
        for entry in entries.filter_map(Result::ok) {
            let path = entry.path();
            if path.is_file() && path.extension().is_some_and(|ext| ext == "rs") {
                files.push(path);
            }
        }
    }
    files.sort();
    files.dedup();
    let mut modules = Vec::new();
    for path in files {
        let relative = match path.strip_prefix(&root) {
            Ok(v) => v.to_string_lossy().replace('\\', "/"),
            Err(_) => continue,
        };
        let source = match fs::read_to_string(&path) {
            Ok(v) => v,
            Err(error) => {
                modules.push(json!({"path": relative, "parser": "rust-syn-ast", "parse_error": error.to_string(),
                    "symbols": [], "imports": [], "routes": []}));
                continue;
            }
        };
        match syn::parse_file(&source) {
            Ok(file) => {
                let mut symbols = Vec::new();
                let mut imports = Vec::new();
                let mut routes = Vec::new();
                scan_items(&file.items, &mut symbols, &mut imports, &mut routes);
                let mut collector = CallCollector::default();
                collector.visit_file(&file);
                modules.push(json!({
                    "path": relative, "parser": "rust-syn-ast", "parse_error": null,
                    "docstring": docs(&file.attrs), "line_count": source.lines().count(),
                    "symbols": symbols, "imports": imports, "routes": routes, "calls": collector.calls
                }));
            }
            Err(error) => modules.push(json!({
                "path": relative, "parser": "rust-syn-ast", "parse_error": error.to_string(),
                "symbols": [], "imports": [], "routes": []
            })),
        }
    }
    println!("{}", json!({"modules": modules}));
}
