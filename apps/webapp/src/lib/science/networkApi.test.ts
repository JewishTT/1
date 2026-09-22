import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { networkApi } from "./api";

function stubFetch(status: number, body: unknown) {
  return vi.fn(async () =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
}

describe("networkApi client (payload contract)", () => {
  const realFetch = global.fetch;

  afterEach(() => {
    global.fetch = realFetch;
  });

  beforeEach(() => vi.clearAllMocks());

  it("posts edges as { source, target, edge_type } to /measures", async () => {
    global.fetch = stubFetch(200, { ok: true });
    const res = await networkApi.measures([{ source: "A", target: "B", edge_type: "possible_match" }]);
    expect(res).toEqual({ ok: true });
    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/api/v1/network/measures");
    expect(JSON.parse(init.body)).toEqual({
      edges: [{ source: "A", target: "B", edge_type: "possible_match" }],
    });
  });

  it("throws a readable error on 422 scope refusal", async () => {
    global.fetch = stubFetch(422, { detail: { error: "scope_refused" } });
    await expect(networkApi.measures([{ source: "A", target: "B" }])).rejects.toThrow("scope_refused");
  });

  it("keeps phodms clouds bounded to six time slices (persistence contract)", async () => {
    global.fetch = stubFetch(200, { n_times: 2 });
    await networkApi.phodms({ clouds: [[[1], [2], [3]], [["8" as unknown as number]]] });
    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/api/v1/network/phodms");
    const body = JSON.parse(init.body);
    expect(body.clouds.length).toBeLessThanOrEqual(6);
  });
});