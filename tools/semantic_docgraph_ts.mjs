import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import process from "node:process";

const args = process.argv.slice(2);
const rootArg = args.indexOf("--root");
const root = path.resolve(rootArg >= 0 ? args[rootArg + 1] : process.cwd());
const require = createRequire(path.join(root, "apps", "webapp", "package.json"));
let ts;
try {
  ts = require("typescript");
} catch (error) {
  process.stderr.write("TypeScript compiler AST is unavailable. Run npm ci in apps/webapp first.\n");
  process.exit(2);
}
const roots = ["apps", "bench", "benchmarks", "tools", "platform_model", "implementation", "specs"];
const excluded = new Set([
  ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
  ".ruff_cache", "target", "dist", "build", "tmp", "logs", "donors",
  "pip-unpack", "pip-metadata"
]);
const extensions = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".scss", ".html"]);
const files = [];
function walk(directory) {
  if (!fs.existsSync(directory)) return;
  const entries = fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
  for (const entry of entries) {
    if (entry.isDirectory()) {
      if (!excluded.has(entry.name)) walk(path.join(directory, entry.name));
    } else if (entry.isFile() && extensions.has(path.extname(entry.name).toLowerCase())) {
      files.push(path.join(directory, entry.name));
    }
  }
}
for (const base of roots) walk(path.join(root, base));
for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
  if (entry.isFile() && extensions.has(path.extname(entry.name).toLowerCase())) {
    files.push(path.join(root, entry.name));
  }
}
const uniqueFiles = [...new Set(files)].sort();
const modules = [];

function cssModule(relative, absolute, text) {
  const postcss = require("postcss");
  const rootNode = postcss.parse(text, { from: absolute });
  const symbols = [];
  const references = [];
  let ordinal = 0;
  const lineOf = (node) => node.source?.start?.line ?? 1;
  function add(kind, name, qualified, line, signature = "") {
    symbols.push({
      name, qualified_name: qualified, kind, line,
      public: !String(name).startsWith("_"), docstring: "", signature
    });
  }
  rootNode.walk((node) => {
    const line = lineOf(node);
    if (node.type === "rule") {
      const selector = String(node.selector || "").trim();
      const key = "selector:" + selector + "@" + line + ":" + ordinal++;
      add("css-rule", selector, key, line, selector);
      for (const match of selector.matchAll(/\.([_a-zA-Z][\w-]*)/g)) {
        add("css-class-selector", match[1], "class:" + match[1] + "@" + line + ":" + ordinal++, line, "." + match[1]);
      }
      for (const match of selector.matchAll(/#([_a-zA-Z][\w-]*)/g)) {
        add("css-id-selector", match[1], "id:" + match[1] + "@" + line + ":" + ordinal++, line, "#" + match[1]);
      }
    } else if (node.type === "atrule") {
      const name = "@" + node.name + (node.params ? " " + node.params : "");
      add("css-at-rule", name, "at-rule:" + name + "@" + line + ":" + ordinal++, line, name);
      if (String(node.name).toLowerCase() === "import") {
        const match = String(node.params || "").match(/^(?:url\(\s*)?["']?([^"')\s]+)["']?\s*\)?/i);
        if (match && !/^(?:https?:|data:|\/\/|#)/i.test(match[1])) {
          references.push({ target: match[1], target_kind: "source-path", kind: "imports-css-source", line });
        }
      }
    } else if (node.type === "decl") {
      const property = String(node.prop || "");
      const parents = [];
      let parent = node.parent;
      while (parent && parent.type !== "root") {
        if (parent.type === "rule" && parent.selector) parents.unshift(String(parent.selector).trim());
        parent = parent.parent;
      }
      const kind = property.startsWith("--") ? "css-custom-property" : "css-declaration";
      const qualified = parents.join(" > ") + "::" + property + "@" + line + ":" + ordinal++;
      add(kind, property, qualified, line, property + ": " + String(node.value || ""));
      for (const match of String(node.value || "").matchAll(/var\(\s*(--[\w-]+)/g)) {
        references.push({ target: match[1], target_kind: "css-custom-property", kind: "uses-css-custom-property", line });
      }
    }
  });
  return {
    path: relative, parser: "postcss-ast", parse_error: null,
    docstring: "", line_count: text.split("\n").length,
    imports: [], symbols, routes: [], calls: [], references
  };
}

function htmlModule(relative, absolute, text) {
  const parse5 = require("parse5");
  const diagnostics = [];
  const document = parse5.parse(text, {
    sourceCodeLocationInfo: true,
    onParseError: (error) => diagnostics.push({
      code: error.code,
      line: error.startLine ?? null,
      column: error.startCol ?? null
    })
  });
  const symbols = [];
  const references = [];
  let ordinal = 0;
  function visit(node, ancestors) {
    if (node.tagName) {
      const tag = String(node.tagName).toLowerCase();
      const attrs = Object.fromEntries((node.attrs || []).map((attr) => [attr.name, attr.value]));
      const line = node.sourceCodeLocation?.startLine ?? 1;
      const classes = String(attrs.class || "").split(/\s+/).filter(Boolean);
      const key = attrs.id ? tag + "#" + attrs.id : tag + (classes.length ? "." + classes.join(".") : "");
      const location = ancestors.concat([key + "@" + line + ":" + ordinal++]).join("/");
      symbols.push({
        name: key, qualified_name: location, kind: "html-element", line,
        public: Boolean(attrs.id) || ["main", "nav", "header", "footer", "form", "button"].includes(tag),
        docstring: "", signature: "<" + tag + ">"
      });
      for (const className of classes) {
        references.push({ target: className, target_kind: "css-selector", kind: "matches-css-class", line });
      }
      if (attrs.id) {
        references.push({ target: attrs.id, target_kind: "css-selector", kind: "matches-css-id", line });
      }
      const localTarget = tag === "script" ? attrs.src
        : tag === "link" ? attrs.href
        : ["img", "source", "video", "audio", "iframe"].includes(tag) ? (attrs.src || attrs.poster)
        : null;
      if (localTarget && !/^(?:[a-z]+:|\/\/|#|data:)/i.test(localTarget)) {
        references.push({ target: localTarget, target_kind: "source-path", kind: "references-html-asset", line });
      }
      const nextAncestors = ancestors.concat([key]);
      for (const child of node.childNodes || []) visit(child, nextAncestors);
      return;
    }
    for (const child of node.childNodes || []) visit(child, ancestors);
    if (node.content) visit(node.content, ancestors);
  }
  visit(document, []);
  return {
    path: relative, parser: "parse5-ast", parse_error: null, diagnostics,
    docstring: "", line_count: text.split("\n").length,
    imports: [], symbols, routes: [], calls: [], references
  };
}

for (const absolute of uniqueFiles) {
  const relative = path.relative(root, absolute).split(path.sep).join("/");
  const text = fs.readFileSync(absolute, "utf8");
  const extension = path.extname(absolute).toLowerCase();
  if (extension === ".css" || extension === ".scss") {
    try {
      modules.push(cssModule(relative, absolute, text));
    } catch (error) {
      modules.push({ path: relative, parser: "postcss-ast", parse_error: String(error.message || error), symbols: [], imports: [], routes: [], calls: [], references: [] });
    }
    continue;
  }
  if (extension === ".html") {
    try {
      modules.push(htmlModule(relative, absolute, text));
    } catch (error) {
      modules.push({ path: relative, parser: "parse5-ast", parse_error: String(error.message || error), symbols: [], imports: [], routes: [], calls: [], references: [] });
    }
    continue;
  }
  const scriptKind = extension === ".tsx" ? ts.ScriptKind.TSX
    : extension === ".jsx" ? ts.ScriptKind.JSX
    : [".js", ".mjs", ".cjs"].includes(extension) ? ts.ScriptKind.JS : ts.ScriptKind.TS;
  const source = ts.createSourceFile(absolute, text, ts.ScriptTarget.Latest, true, scriptKind);
  const parseErrors = (source.parseDiagnostics || []).map((diagnostic) => {
    const message = ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n");
    const line = diagnostic.start == null ? null : source.getLineAndCharacterOfPosition(diagnostic.start).line + 1;
    return { message, line };
  });
  const imports = [];
  const symbols = [];
  const routes = [];
  const calls = [];
  const kindName = (node) => {
    if (ts.isFunctionDeclaration(node)) return "function";
    if (ts.isClassDeclaration(node)) return "class";
    if (ts.isInterfaceDeclaration(node)) return "interface";
    if (ts.isTypeAliasDeclaration(node)) return "type";
    if (ts.isEnumDeclaration(node)) return "enum";
    if (ts.isMethodDeclaration(node)) return "method";
    if (ts.isPropertyDeclaration(node)) return "property";
    if (ts.isVariableDeclaration(node)) return "variable";
    if (ts.isModuleDeclaration(node)) return "namespace";
    if (ts.isConstructorDeclaration(node)) return "constructor";
    return null;
  };
  const named = (node) => {
    if (node.name && (ts.isIdentifier(node.name) || ts.isStringLiteral(node.name) || ts.isNumericLiteral(node.name))) {
      return node.name.text;
    }
    return null;
  };
  const isExported = (node) => {
    let carrier = node;
    if (ts.isVariableDeclaration(node) && node.parent && node.parent.parent) carrier = node.parent.parent;
    if (!ts.canHaveModifiers(carrier)) return false;
    return (ts.getModifiers(carrier) || []).some((modifier) =>
      modifier.kind === ts.SyntaxKind.ExportKeyword || modifier.kind === ts.SyntaxKind.DefaultKeyword
    );
  };
  const lineOf = (node) => source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
  function visit(node, scope) {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) {
      const specifier = node.moduleSpecifier;
      if (specifier && (ts.isStringLiteral(specifier) || ts.isNoSubstitutionTemplateLiteral(specifier))) {
        imports.push({ specifier: specifier.text, line: lineOf(node), kind: ts.isImportDeclaration(node) ? "import" : "export" });
      }
    }
    const kind = kindName(node);
    const name = kind ? named(node) : null;
    let childScope = scope;
    if (kind && name) {
      const qualified = scope.concat([name]).join(".");
      const doc = ts.getJSDocCommentsAndTags(node);
      const docstring = doc.length ? doc.map((item) => item.getText(source).replace(/^\/\*\*?|\*\/$/g, "").trim()).join(" ").slice(0, 240) : "";
      symbols.push({
        name, qualified_name: qualified, kind, line: lineOf(node),
        public: !name.startsWith("_"), exported: isExported(node), docstring
      });
      if (["function", "class", "interface", "enum", "namespace"].includes(kind)) childScope = scope.concat([name]);
    }
    if (ts.isCallExpression(node)) {
      const target = node.expression.getText(source);
      calls.push({ callee: target, line: lineOf(node) });
      const leaf = target.split(".").pop().toLowerCase();
      const arg = node.arguments[0];
      if (["get", "post", "put", "patch", "delete", "head", "options"].includes(leaf) &&
          arg && (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg)) &&
          arg.text.startsWith("/")) {
        routes.push({ method: leaf.toUpperCase(), path: arg.text, line: lineOf(node), caller: target });
      }
      if (["fetch", "request", "usequery", "usemutation"].includes(leaf)) {
        routes.push({ method: "CALL", path: arg && (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg)) ? arg.text : target,
          line: lineOf(node), caller: target });
      }
    }
    ts.forEachChild(node, (child) => visit(child, childScope));
  }
  visit(source, []);
  modules.push({
    path: relative, parser: "typescript-compiler-ast", parse_error: parseErrors.length ? JSON.stringify(parseErrors.slice(0, 10)) : null,
    docstring: "", line_count: text.split("\n").length, imports, symbols, routes, calls,
    diagnostics: parseErrors
  });
}
process.stdout.write(JSON.stringify({ modules }));
