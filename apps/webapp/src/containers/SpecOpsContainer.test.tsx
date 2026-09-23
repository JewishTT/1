import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SpecOpsContainer } from "./SpecOpsContainer";

const GRAPH = {
  nodes: [
    { id: "e-1", label: "alice@example.com", entity_type: "EMAIL", properties: { email: "alice@example.com" } },
    { id: "e-2", label: "bob", entity_type: "USERNAME", properties: { username: "bob" } },
  ],
  edges: [{ id: "rel-1", source: "e-1", target: "e-2", kind: "related_to" }],
};

const TOOLS = {
  tools: [
    {
      tool_id: "email-enrich",
      name: "EmailEnrich",
      category: "Enrichment",
      entity_types: ["EMAIL"],
      method: "API",
      source: "example",
      license: "MIT",
      attribution: "",
      run_mode: "sync",
      command_template: ["example/email-artist", "%ENTITY_VALUE%", "%ENTITY_TYPE%"],
      description: "Enrich an email address.",
    },
    {
      tool_id: "user-lookup",
      name: "UserLookup",
      category: "Recon",
      entity_types: ["USERNAME"],
      method: "API",
      source: "example",
      license: "MIT",
      attribution: "",
      run_mode: "async",
      command_template: ["example/user-artist", "%ENTITY_VALUE%"],
      description: "Look up a username.",
    },
  ],
};

const EMAIL_TAP = {
  target: {
    id: () => "e-1",
    data: () => ({
      id: "e-1",
      label: "alice@example.com",
      entity_type: "EMAIL",
      entity_value: "alice@example.com",
    }),
  },
};

// Captured from the SpecOpsGraphPanel cytoscape mount (`cy.on("tap", "node", …)`).
const mockNodeTap: {
  current: ((evt: { target: { id: () => string; data: () => Record<string, unknown> } }) => void) | null;
} = { current: null };

vi.mock("cytoscape", () => ({
  default: () => ({
    on: (event: string, _a: unknown, b?: unknown) => {
      if (event === "tap" && typeof b === "function") {
        mockNodeTap.current = b as typeof mockNodeTap.current;
      }
    },
    fit: () => {},
    getElementById: (_id: string) => ({ length: 0 }),
    $: () => ({ unselect: () => {} }),
    destroy: () => {},
  }),
}));

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

describe("SpecOpsContainer", () => {
  beforeEach(() => {
    mockNodeTap.current = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/entities/graph")) return jsonResponse(GRAPH);
      if (url.includes("/tools/") && url.endsWith("/enqueue")) {
        return jsonResponse({
          run: {
            tool_id: "email-enrich",
            entity_type: "EMAIL",
            entity_value: "alice@example.com",
            entity_id: "e-1",
            status: "QUEUED",
            command: ["example/email-artist", "alice@example.com", "EMAIL"],
          },
          event: "tool.run_enqueued",
        });
      }
      if (url.includes("/tools")) return jsonResponse(TOOLS);
      return jsonResponse({ detail: "not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads the graph and shows the idle toolbar hint before any selection", async () => {
    render(<SpecOpsContainer />);
    const page = await screen.findByTestId("specops-page");
    expect(page).toBeInTheDocument();
    expect(screen.getByTestId("specops-counts")).toHaveTextContent("2 ENTITIES · 1 EDGES");
    expect(screen.getByTestId("toolbar-hint")).toHaveTextContent("Select an entity node");
  });

  it("selecting an entity node arms only the tools for that type", async () => {
    render(<SpecOpsContainer />);
    await screen.findByTestId("specops-page");
    await waitFor(() => expect(mockNodeTap.current).toBeTruthy());

    // Drive the canvas tap through the captured handler — jsdom cannot emit
    // real pointer events into a Cytoscape canvas.
    await act(async () => {
      mockNodeTap.current!(EMAIL_TAP);
    });

    const toolbar = await screen.findByTestId("entity-toolbar");
    expect(within(toolbar).getByTestId("toolbar-type")).toHaveTextContent("EMAIL");
    expect(within(toolbar).getByTestId("toolbar-entity-name")).toHaveTextContent("alice@example.com");
    expect(screen.getByTestId("specops-tool-email-enrich")).toBeInTheDocument();
    expect(screen.queryByTestId("specops-tool-user-lookup")).not.toBeInTheDocument();
    expect(screen.queryByTestId("toolbar-hint")).not.toBeInTheDocument();
  });

  it("enqueues a tool run and renders status + command", async () => {
    render(<SpecOpsContainer />);
    await screen.findByTestId("specops-page");
    await waitFor(() => expect(mockNodeTap.current).toBeTruthy());
    await act(async () => {
      mockNodeTap.current!(EMAIL_TAP);
    });

    fireEvent.click(await screen.findByTestId("specops-tool-email-enrich"));

    await waitFor(() => expect(screen.getByTestId("run-status")).toHaveTextContent("QUEUED"));
    expect(screen.getByTestId("run-tool")).toHaveTextContent("email-enrich");
    expect(screen.getByTestId("run-command")).toHaveTextContent(
      "example/email-artist alice@example.com EMAIL",
    );

    const fetchMock = vi.mocked(global.fetch);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/tools/email-enrich/enqueue"),
      expect.objectContaining({ method: "POST" }),
    );
    const body = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/enqueue"),
    )?.[1];
    expect(JSON.parse(String(body?.body))).toEqual({
      entity_type: "EMAIL",
      entity_value: "alice@example.com",
      entity_id: "e-1",
    });
  });
});