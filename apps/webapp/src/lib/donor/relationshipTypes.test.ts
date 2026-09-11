import { describe, expect, it } from "vitest";

import { isRelationshipAllowed, lookupRelationshipType, relationshipTypes } from "./relationshipTypes";

describe("canonical relationship taxonomy", () => {
  it("names canonical families, not subtypes, at the top level", () => {
    const ids = new Set(relationshipTypes.map((relationship) => relationship.id));

    expect(ids.has("communicated_with")).toBe(true);
    expect(ids.has("case_or_incident_role")).toBe(true);
    expect(ids.has("called")).toBe(false);
    expect(ids.has("emailed")).toBe(false);
    expect(ids.has("works_for")).toBe(false);
    expect(ids.has("member_of")).toBe(false);
    expect(ids.has("paid")).toBe(false);
  });

  it("enforces source and target type constraints", () => {
    const employment = lookupRelationshipType("employment_or_affiliation");
    const caseRole = lookupRelationshipType("case_or_incident_role");

    expect(employment).toBeDefined();
    expect(caseRole).toBeDefined();

    expect(isRelationshipAllowed(employment!, "person", "organization")).toBe(true);
    expect(isRelationshipAllowed(employment!, "organization", "person")).toBe(false);
    expect(isRelationshipAllowed(caseRole!, "person", "incident")).toBe(true);
    expect(isRelationshipAllowed(caseRole!, "domain", "incident")).toBe(false);
  });

  it("defaults safely for unknown ids", () => {
    expect(lookupRelationshipType("does_not_exist")).toBeUndefined();
  });

  it("exposes human labels for known relations", () => {
    expect(lookupRelationshipType("associated_with")?.label).toBe("Associated With");
  });
});