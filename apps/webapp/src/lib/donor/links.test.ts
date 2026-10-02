import { describe, expect, it } from "vitest";

import {
  LINK_ROLE_BY_KIND,
  formatLinkReason,
  linkColor,
  linkRole,
  reportLag,
  type LinkPalette,
} from "./links";

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

/**
 * The edge palette, supplied by the caller rather than baked into the module
 * (T135). These are the `--c-*` values `styles/legacy/legacy-tokens.css`
 * declares, spelled out so the test can assert the ROLE MAPPING rather than the
 * colour — which is the part that is ours.
 */
const PALETTE: LinkPalette = {
  accent: "accent-token",
  accentAlt: "accent-alt-token",
  muted: "muted-token",
  border: "border-token",
  danger: "danger-token",
  success: "success-token",
};

describe("linkColor — a kind maps to a ROLE, and the caller's palette supplies the value", () => {
  it("maps known kinds to their roles", () => {
    expect(linkRole("possible_match")).toBe("info");
    expect(linkRole("same_as")).toBe("accent");
    expect(linkRole("alias_of")).toBe("accent");
    expect(linkRole("event_followed_by")).toBe("warning");
    expect(linkRole("located_at")).toBe("warning");
    expect(linkRole("mentioned_with")).toBe("muted");
    expect(linkRole("associated_with")).toBe("neutral");
  });

  it("resolves a role to the token the palette supplies", () => {
    expect(linkColor("possible_match", PALETTE)).toBe(PALETTE.accent);
    expect(linkColor("same_as", PALETTE)).toBe(PALETTE.success);
    expect(linkColor("event_followed_by", PALETTE)).toBe(PALETTE.accentAlt);
    expect(linkColor("mentioned_with", PALETTE)).toBe(PALETTE.muted);
  });

  it("uses a neutral default for unknown kinds", () => {
    expect(linkRole("mystery")).toBe("neutral");
    expect(linkColor("mystery", PALETTE)).toBe(PALETTE.border);
  });

  it("contains no hex literal of its own, so a theme change reaches the edges", () => {
    // The previous form was a `Record<string, string>` of hex. Asserting the
    // absence of `#` in the source is crude but it is the assertion that fails
    // when somebody adds one back, which is the regression this change exists to
    // prevent.
    const source = LINK_ROLE_BY_KIND;
    expect(Object.keys(source).length).toBeGreaterThan(0);
    expect(JSON.stringify(source)).not.toContain("#");
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