import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SearchPage, SearchResult } from "./SearchPage";

function result(id: string, backend: string): SearchResult {
  return {
    doc_id: id,
    score: 0.8,
    backends: [backend],
    observation_ids: ["OBS-1"],
    evidence: [
      {
        backend,
        kind: "observation",
        observation: { observation_id: "OBS-1", uri: "http://src", immutable: true },
        source_id: "src-a",
        reason: "match",
      },
    ],
  };
}

describe("SearchPage", () => {
  it("runs a hybrid query and shows fused results", async () => {
    const onSearch = vi.fn(async () => [result("OBS-1001", "opensearch")]);
    render(<SearchPage onSearch={onSearch} />);
    fireEvent.change(screen.getByTestId("query-input"), { target: { value: "Yard" } });
    fireEvent.submit(screen.getByTestId("search-page").querySelector("form")!);
    await waitFor(() => expect(screen.getByTestId("result-list")).toBeInTheDocument());
    expect(screen.getByText("OBS-1001")).toBeInTheDocument();
    expect(onSearch).toHaveBeenCalledWith("Yard", "");
    expect(screen.getByTestId("obs-count")).toHaveTextContent("1");
  });

  it("passes the source filter through", async () => {
    const onSearch = vi.fn(async () => [result("OBS-2", "clickhouse")]);
    render(<SearchPage onSearch={onSearch} />);
    fireEvent.change(screen.getByTestId("query-input"), { target: { value: "ledger" } });
    fireEvent.change(screen.getByTestId("source-filter"), { target: { value: "src-a" } });
    fireEvent.submit(screen.getByTestId("search-page").querySelector("form")!);
    await waitFor(() => expect(screen.getByTestId("result-list")).toBeInTheDocument());
    expect(onSearch).toHaveBeenCalledWith("ledger", "src-a");
  });

  it("shows evidence link anchored to an immutable observation", async () => {
    const onSearch = vi.fn(async () => [result("OBS-1001", "opensearch")]);
    render(<SearchPage onSearch={onSearch} />);
    fireEvent.change(screen.getByTestId("query-input"), { target: { value: "Yard" } });
    fireEvent.submit(screen.getByTestId("search-page").querySelector("form")!);
    await waitFor(() => expect(screen.getByTestId("evidence-link")).toBeInTheDocument());
    const link = screen.getByTestId("evidence-link");
    expect(link.textContent).toContain("OBS-1");
    expect(link.textContent).not.toContain("broken");
  });
});
