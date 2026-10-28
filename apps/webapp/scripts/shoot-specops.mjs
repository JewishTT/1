/**
 * Deterministic responsive screenshot sweep for CI/SpecOps + GhostLine.
 *
 * The UI is rendered by the real Vite app. Read-only API replies are provided
 * by Playwright fixtures because CI intentionally does not start the control
 * plane. Fixture values are explicitly marked as screenshot-only and never
 * live in the production bundle. Any unknown API read or attempted mutation
 * fails the sweep instead of leaving an endless loading skeleton on screen.
 *
 * Usage: node scripts/shoot-specops.mjs [baseUrl] [outDir]
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const BASE = process.argv[2] ?? "http://127.0.0.1:5173";
const OUT = process.argv[3] ?? join(tmpdir(), "cognitive-ui-shots");
const CHROME = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;

const DEPARTMENT_PANELS = [
  ["Operations", "operations", "ci-operations"],
  ["Kill-chain", "emulation", "ci-emulation"],
  ["Phishing / SAT", "phishing", "ci-phishing"],
  ["APT forensics", "forensics", "ci-forensics"],
  ["Detection", "detection", "ci-detection"],
  ["Counterintel", "counterintel", "ci-counterintel"],
  ["Social reaction", "social", "ci-social"],
  ["GhostLine", "ghostline", "gl-runtime"],
];

const GHOSTLINE_PANELS = [
  ["Playbooks", "playbooks", "gl-playbooks"],
  ["Simulator", "simulate", "gl-simulate"],
  ["Voices", "voices", "gl-voices"],
  ["Dialler", "dialer", "gl-dialer"],
  ["Engagement", "engagement", "gl-engagement"],
  ["Transcripts", "transcripts", "gl-transcripts"],
  ["Analytics", "analytics", "gl-analytics"],
];

const VIEWPORTS = [
  [2560, 1440, "ultrawide"],
  [1920, 1080, "wide"],
  [1440, 900, "baseline"],
  [1100, 900, "narrow"],
  [1023, 900, "tablet"],
  [767, 900, "small-tablet"],
  [390, 844, "phone"],
];

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({
  ...(CHROME ? { executablePath: CHROME } : {}),
  headless: true,
});
const page = await browser.newPage({
  viewport: { width: 1680, height: 1050 },
  deviceScaleFactor: 1,
});

const problems = [];
const fixtureRequests = [];
const manifest = [];

page.on("console", (message) => {
  const value = message.text();
  if (message.type() === "error" && !value.includes("404")) {
    problems.push("console: " + value.slice(0, 220));
  }
});
page.on("pageerror", (error) => problems.push("pageerror: " + error.message.slice(0, 220)));
page.on("requestfailed", (request) => {
  problems.push("request failed: " + request.method() + " " + request.url() + " " + request.failure()?.errorText);
});

/* Fixture objects below are browser-test data, never production application data. */
function investigationFixture(id) {
  return {
    investigation_id: id,
    name: "VISUAL REGRESSION / " + id.toUpperCase(),
    tenant_id: "screenshot-fixture",
    objective: { type: "visual-fixture", description: "Playwright screenshot regression only." },
    seeds: [],
    scope: { fixture: true },
    policy_id: null,
    state: "RUNNING",
    created_at: "2026-10-28T00:00:00Z",
  };
}

const metricsFixture = {
  throughput_per_s: 42.8,
  useful_observations: 12842,
  discovery_yield: 0.42,
  duplicate_ratio: 0.03,
  browser_utilization: 0.64,
  lags_s: { ingest: 1.2, extract: 8.4, resolve: 37.1 },
  queues: { frontier: 1240, enrichment: 8, admission: 3 },
  storage_growth_b: { raw_artifacts: 134217728, lakehouse: 33554432 },
  cost_per_1m_obs: 4.25,
};

const poolsFixture = {
  pools: {
    capture: { healthy: true, active: 4, capacity: 8, failures: 0 },
    extract: { healthy: true, active: 7, capacity: 8, failures: 1 },
    resolve: { healthy: true, active: 2, capacity: 4, failures: 0 },
  },
  healthy: ["capture", "extract", "resolve"],
};

const playbookFixture = {
  playbook_id: "screenshot-fixture-runbook",
  name: "Visual fixture scenario",
  author: "screenshot-fixture",
  version: 1,
  culture: "en",
  description: "Read-only fixture used to verify panel layout.",
  stage_count: 1,
  first_stage: "INIT",
  stage_names: ["INIT"],
  has_branching: false,
  persona_name: "fixture",
  techniques: [],
  mapping_source: "platform-declared",
  source_path: "screenshot-fixture",
  valid: true,
  invalid_reason: null,
  missing: [],
};

const statusFixture = {
  served: ["donor", "runtime", "providers", "counts"],
  missing: ["Live media integrations and deployment credentials are not configured in the screenshot runner."],
  scope: "tenant-wide",
  donor: {
    donor_id: "ghostline",
    repo: "screenshot-fixture",
    license: "not reported",
    root: "screenshot-fixture",
    present: true,
    playbooks_root: "screenshot-fixture/playbooks",
    stage_engine: { ready: ["taxonomy", "transition runner", "redaction"], absent: [] },
    live_edges: { ready: [], absent: ["STT provider", "TTS provider", "telephony route", "public media tunnel"] },
    roles: {},
  },
  config: {
    model: "not configured",
    litellm_api_base: null,
    tts_model: "not configured",
    stt_model: "not configured",
    stt_language: "en",
    samples_root: "screenshot-fixture",
    playbooks_root: "screenshot-fixture/playbooks",
    ledger_path: "screenshot-fixture/ledger",
    log_level: "INFO",
  },
  providers: [
    { name: "Speech-to-text", configured: false, env_var: "DEEPGRAM_API_KEY", detail: "Not configured in the screenshot runner." },
    { name: "Text-to-speech", configured: false, env_var: "ELEVENLABS_API_KEY", detail: "Not configured in the screenshot runner." },
    { name: "Telephony", configured: false, env_var: "TWILIO_AUTH_TOKEN", detail: "Not configured in the screenshot runner." },
  ],
  blockers: ["Provider credentials are not configured.", "Live telephony and media routes are unavailable."],
  runtime: {
    state: "blocked",
    voice_id: null,
    voice_name: null,
    playbook_id: null,
    playbook_name: null,
    model: null,
    capabilities: {
      modality: "hybrid_stt",
      native_stt: false,
      native_tts: false,
      needs_deepgram: true,
      needs_elevenlabs: true,
    },
    ws_url: null,
    public_url: null,
    tunnel_provider: null,
    port: null,
    started_at: null,
    media_route_served: false,
    blockers: ["Provider credentials are not configured.", "Live telephony and media routes are unavailable."],
    missing: ["GET /api/v1/specops/ghostline/status is represented by a read-only screenshot fixture, not a live backend."],
  },
  counts: { playbooks: 1, playbooks_valid: 1, voices: 1, calls: 0 },
  playbook_validation_errors: {},
};

const taxonomyFixture = {
  served: ["events", "stages"],
  missing: [],
  scope: "tenant-wide",
  events: [],
  stages: [
    { key: "opened", stage: 1, intent: "Opened" },
    { key: "clicked", stage: 2, intent: "Clicked" },
    { key: "submitted", stage: 3, intent: "Submitted" },
  ],
  dont_heritage: [],
  log_path: "screenshot-fixture",
};

const analyticsFixture = {
  served: ["call_count", "completed_count", "stage_counts", "outcomes"],
  missing: ["No calls exist in the screenshot fixture."],
  scope: "tenant-wide",
  analytics: {
    campaign: null,
    call_count: 0,
    completed_count: 0,
    in_progress_count: 0,
    turn_count: 0,
    stage_counts: {},
    outcomes: {},
    by_campaign: {},
    redaction_kinds: {},
    capture_passwords: false,
    credentials_captured: 0,
    conversion_rate: null,
  },
};

const boardFixture = {
  served: ["campaigns", "subjects", "stages"],
  missing: ["No engagement events exist in the screenshot fixture."],
  scope: "tenant-wide",
  projection: {
    campaigns: [],
    subjects: [],
    outcome_split: {},
    stages: taxonomyFixture.stages,
    missing: ["No channel has reported an engagement event in the screenshot fixture."],
  },
};

const responseFixtures = new Map([
  ["/api/v1/metrics", metricsFixture],
  ["/api/v1/metrics/pools", poolsFixture],
  ["/api/v1/dlq", { tenant_id: "screenshot-fixture", records: [] }],
  ["/api/v1/connectors", { connectors: [] }],
  ["/api/v1/specops/emulation/plans", {
    served: ["plans"],
    missing: [],
    scope: "tenant-wide",
    plans: [
      {
        plan_id: "screenshot-fixture-discovery",
        name: "Fixture discovery baseline",
        source_donor: "screenshot-fixture",
        target_techniques: ["T1046", "T1018"],
        lab_fixture: "isolated-screenshot-fixture",
      },
      {
        plan_id: "screenshot-fixture-collection",
        name: "Fixture collection verification",
        source_donor: "screenshot-fixture",
        target_techniques: ["T1057"],
        lab_fixture: "isolated-screenshot-fixture",
      },
    ],
  }],
  ["/api/v1/specops/ghostline/status", statusFixture],
  ["/api/v1/specops/ghostline/playbooks", {
    served: ["playbooks"],
    missing: [],
    scope: "tenant-wide",
    playbooks: [playbookFixture],
    invalid: {},
  }],
  ["/api/v1/specops/ghostline/voices", {
    served: ["voices"],
    missing: [],
    scope: "tenant-wide",
    voices: [{
      voice_id: "screenshot-fixture-voice",
      name: "Fixture voice",
      origin: "premade",
      created_at: "2026-10-28T00:00:00Z",
      sample_ref: null,
      sample_bytes: null,
      notes: "Screenshot fixture only; no voice provider is contacted.",
    }],
  }],
  ["/api/v1/specops/ghostline/calls", {
    served: ["calls"],
    missing: ["No calls exist in the screenshot fixture."],
    scope: "tenant-wide",
    calls: [],
  }],
  ["/api/v1/specops/ghostline/analytics", analyticsFixture],
  ["/api/v1/specops/engagement/board", boardFixture],
  ["/api/v1/specops/engagement/taxonomy", taxonomyFixture],
]);

await page.route("**/api/**", async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  const method = request.method();
  const apiPath = url.pathname;
  let status = 200;
  let body;

  if (method !== "GET") {
    status = 409;
    body = { detail: "Screenshot fixture blocks mutating requests: " + method + " " + apiPath };
    problems.push("unexpected mutating API request: " + method + " " + apiPath);
  } else if (/^\/api\/v1\/investigations\/[^/]+$/.test(apiPath)) {
    body = investigationFixture(decodeURIComponent(apiPath.split("/").at(-1) || "fixture"));
  } else if (responseFixtures.has(apiPath)) {
    body = responseFixtures.get(apiPath);
  } else {
    status = 501;
    body = { detail: "No screenshot fixture registered for GET " + apiPath };
    problems.push("unmapped screenshot API request: GET " + apiPath);
  }

  fixtureRequests.push({ method, path: apiPath, query: url.search, status });
  await route.fulfill({
    status,
    contentType: "application/json; charset=utf-8",
    body: JSON.stringify(body),
  });
});

async function screenshot(name, extra = {}) {
  await page.evaluate(() => document.fonts.ready.then(() => true));
  await page.waitForTimeout(180);
  const metrics = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    shell: Boolean(document.querySelector('[data-testid="app-shell"]')),
    ciCanvas: Boolean(document.querySelector('[data-testid="ci-canvas"]')),
    ghostlineCanvas: Boolean(document.querySelector('[data-testid="gl-canvas"]')),
    topbar: (() => {
      const element = document.querySelector('[data-testid="app-shell-topbar"]');
      const rect = element?.getBoundingClientRect();
      return rect ? { top: rect.top, bottom: rect.bottom, height: rect.height } : null;
    })(),
    bodyStart: document.querySelector(".ui-shell-body")?.getBoundingClientRect().top ?? null,
    theme: document.querySelector(".ui-shell")?.getAttribute("data-theme") ?? null,
    density: document.querySelector(".ui-shell")?.getAttribute("data-density") ?? null,
    text: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 180),
  }));
  const filename = name + ".png";
  await page.screenshot({ path: join(OUT, filename), fullPage: false, animations: "disabled" });
  const report = { filename, ...metrics, ...extra };
  manifest.push(report);
  process.stdout.write(JSON.stringify(report) + "\n");

  if (!metrics.shell) problems.push(name + ": app shell did not mount");
  if (metrics.document > metrics.viewport + 1 || metrics.body > metrics.viewport + 1) {
    problems.push(name + ": horizontal overflow (viewport=" + metrics.viewport + ", document=" + metrics.document + ", body=" + metrics.body + ")");
  }
  if (metrics.topbar && metrics.bodyStart !== null && metrics.topbar.bottom > metrics.bodyStart + 1) {
    problems.push(name + ": shell body begins underneath top bar (header bottom=" + metrics.topbar.bottom + ", body starts=" + metrics.bodyStart + ")");
  }
  return report;
}

async function clickAndWait(tabScope, rootSelector, label, attribute, expected) {
  const selector = tabScope + ' [role="tab"]:has-text("' + label + '")';
  const tab = page.locator(selector).first();
  if (await tab.count() === 0) {
    problems.push("missing tab: " + label + " in " + tabScope);
    return false;
  }
  await tab.click();
  await page.waitForFunction(
    ({ root, attr, value }) => document.querySelector(root)?.getAttribute(attr) === value,
    { root: rootSelector, attr: attribute, value: expected },
    { timeout: 20000 },
  ).catch(() => problems.push("tab did not become active: " + label + " (expected " + expected + ")"));
  await page.waitForTimeout(300);
  return true;
}

try {
  await page.goto(new URL("/investigations/ci", BASE).href, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForSelector('[data-testid="app-shell"]', { timeout: 20000 });
  await page.waitForSelector('[data-testid="app-shell-topbar"]', { timeout: 20000 });

  await page.getByRole("tab", { name: /CI \/ SpecOps/i }).click();
  await page.waitForSelector('[data-testid="ci-canvas"]', { timeout: 20000 });
  await page.getByTestId("ops-attention").waitFor({ timeout: 20000 });
  await page.getByTestId("ops-pools").waitFor({ timeout: 20000 });
  await page.getByTestId("topbar-investigation-name").waitFor({ timeout: 20000 });
  await screenshot("00-department", { surface: "CI / SpecOps", fixtureMode: true });

  for (const [label, panel, name] of DEPARTMENT_PANELS) {
    if (panel === "operations") continue;
    await clickAndWait(".ui-cicanvas-head", '[data-testid="ci-canvas"]', label, "data-panel", panel);
    await screenshot(name, { surface: label, fixtureMode: true });
  }

  // The department's GhostLine tab mounts a second row of tabs of its own.
  await page.locator('[data-testid="gl-canvas"]').waitFor({ timeout: 20000 });
  await screenshot("gl-runtime", { surface: "GhostLine / Runtime", fixtureMode: true });
  for (const [label, panel, name] of GHOSTLINE_PANELS) {
    await clickAndWait(".ui-gl-subhead", '[data-testid="gl-canvas"]', label, "data-panel", panel);
    await screenshot(name, { surface: "GhostLine / " + label, fixtureMode: true });
  }

  // Toggle through the application's command palette so the screenshot validates
  // the actual store-to-DOM path, not a manually edited attribute.
  await page.locator('.ui-gl-subhead [role="tab"]:has-text("Runtime")').first().click();
  await page.keyboard.press("Control+k");
  await page.getByTestId("command-palette-input").waitFor({ timeout: 10000 });
  await page.keyboard.fill("Toggle theme");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector(".ui-shell")?.getAttribute("data-theme") === "light", null, { timeout: 10000 })
    .catch(() => problems.push("theme toggle did not switch the shell to light mode"));
  await screenshot("gl-runtime-light", { surface: "GhostLine / Runtime", expectedTheme: "light", fixtureMode: true });

  // Restore dark theme for the responsive sweep.
  await page.keyboard.press("Control+k");
  await page.getByTestId("command-palette-input").waitFor({ timeout: 10000 });
  await page.keyboard.fill("Toggle theme");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector(".ui-shell")?.getAttribute("data-theme") === "dark", null, { timeout: 10000 })
    .catch(() => problems.push("theme toggle did not restore dark mode"));
  await page.locator('[data-testid="gl-canvas"]').waitFor({ timeout: 20000 });
  await page.locator(".ui-gl-subhead [role='tab']:has-text('Runtime')").first().click();
  await page.waitForFunction(() => document.querySelector('[data-testid="gl-canvas"]')?.getAttribute("data-panel") === "runtime", null, { timeout: 10000 });

  for (const [width, height, label] of VIEWPORTS) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(350);
    await screenshot("gl-runtime-" + label, { surface: "GhostLine / Runtime", fixtureMode: true });
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('[data-testid="gl-canvas"]').waitFor({ timeout: 10000 });
  const fixtureMutations = fixtureRequests.filter((request) => request.method !== "GET");
  const fixtureFailures = fixtureRequests.filter((request) => request.status >= 400);
  if (fixtureMutations.length > 0) problems.push("screenshot suite attempted a mutating API request");
  if (fixtureFailures.length > 0) {
    problems.push("screenshot API fixtures failed: " + fixtureFailures.map((item) => item.status + " " + item.method + " " + item.path).join(", "));
  }
} catch (error) {
  problems.push("screenshot sweep aborted: " + String(error));
} finally {
  await browser.close();
}

writeFileSync(join(OUT, "manifest.json"), JSON.stringify({ manifest, fixtureRequests, problems }, null, 2));
process.stdout.write("\nScreenshot fixture requests (" + fixtureRequests.length + "):\n");
for (const request of fixtureRequests) {
  process.stdout.write("  " + request.status + " " + request.method + " " + request.path + request.query + "\n");
}

if (problems.length) {
  process.stderr.write("\n" + problems.length + " issue(s):\n" + problems.join("\n") + "\n");
  process.exitCode = 1;
} else {
  process.stdout.write("\nNo API fixture, browser-console, page-error or document-overflow issues. Screenshots: " + OUT + "\n");
}
