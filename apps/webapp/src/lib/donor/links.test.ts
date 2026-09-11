import { describe, expect, it } from "vitest";

import { formatLinkReason, linkColor, reportLag } from "./links";

describe("formatLinkReason", () => {
  it("formats donor-style siem reasons", () => {
    expect(formatLinkReason("shared_cve:CVE-2024-0001")).toBe("Shared CVE-2024-0001");
    expect(formatLinkReason("shared_entity:ACME")).toBe("Shared actor: ACME");
    expect(formatLinkReason("shared_country:UA")).toBe("Shared geography (UA)");
  });

  it("falls back to underscore→space", () => {
    expect(formatLinkReason("name_prefix")).toBe("name prefix");
    expect(formatLinkReason("email_domain")).toBe("email domain");
  });

  it("passes plain phrases through unchanged", () => {
    expect(formatLinkReason("backed by")).toBe("backed by");
  });
});

describe("linkColor", () => {
  it("maps known kinds to stable colours", () => {
    expect(linkColor("possible_match")).toBe("#7aa2c2");
    expect(linkColor("same_as")).toBe("#2e7d4f");
  });

  it("uses a neutral default for unknown kinds", () => {
    expect(linkColor("mystery")).toBe("#888888");
  });
});

describe("reportLag", () => {
  it("renders minutes, hours and days", () => {
    expect(reportLag("2026-01-01T00:00:00Z", "2026-01-01T00:45:00Z")).toBe("+45m");
    expect(reportLag("2026-01-01T00:00:00Z", "2026-01-01T04:15:00Z")).toBe("+4.3h");
    expect(reportLag("2026-01-01T00:00:00Z", "2026-01-04T00:00:00Z")).toBe("+3d");
  });

  it("returns null for the first report or unparsable input", () => {
    expect(reportLag("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")).toBeNull();
    expect(reportLag("nope", "2026-01-01T00:00:00Z")).toBeNull();
  });
});