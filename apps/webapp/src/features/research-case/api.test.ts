import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/http";
import {
  api,
  createCase,
  proposeScopeRevision,
  type CreateCaseRequest,
} from "./api";

const baseCaseRequest: CreateCaseRequest = {
  purpose_code: "public_professional",
  purpose_text: "Verify a publicly documented professional role",
  basis_ref: "approval-record:TEST",
  launch_profile: "PUBLIC_PROFESSIONAL",
  subject_anchors: [{ kind: "public_name", value: "Public Example" }],
  jurisdictions: ["LV"],
  valid_time: { from: "2024-01-01", until: null, precision: "day" },
  claim_families: ["public_professional_role"],
  allowed_source_ids: ["crossref_works"],
  denied_claim_families: [],
  questions: ["Which public record supports this role?"],
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Feature 034 API client", () => {
  it("posts a draft to the canonical research-case endpoint", async () => {
    const response = {
      case_id: "ctx-sha256-test",
      tenant_id: "tenant-test",
      state: "DRAFT",
      scope_digest: "sha256:test",
      scope_revision: 1,
      created_at: "2026-10-25T00:00:00Z",
      obligation_count: 3,
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(response), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(createCase(baseCaseRequest)).resolves.toEqual(response);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe("/api/v1/research-cases");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(baseCaseRequest);
  });

  it("encodes the case identifier and sends full revised scope", async () => {
    const response = {
      case_id: "case/test",
      scope_revision: 2,
      scope_digest: "sha256:revision-two",
      re_approval_required: true,
      stale_scope_behavior: "CANCELLED_STALE_SCOPE",
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(response), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(proposeScopeRevision("case/test", baseCaseRequest)).resolves.toEqual(response);
    expect(fetchSpy.mock.calls[0][0]).toBe("/api/v1/research-cases/case%2Ftest/scope");
    expect(fetchSpy.mock.calls[0][1]?.method).toBe("PATCH");
  });

  it("preserves the 503 capability blocker as an actionable ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "coverage projection is not composed" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const error = await api.getCoverage("case-123").catch((value: unknown) => value);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      name: "ApiError",
      status: 503,
      message: "coverage projection is not composed",
    });
  });
});
