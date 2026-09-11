import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { QuarantineRecord } from "../lib/api";
import { QuarantinePage } from "./QuarantinePage";

const record: QuarantineRecord = {
  record_id: "DLQ-1",
  reason: "parse-failure",
  topic: "cognitive-events--t-default-tenant",
  partition: 0,
  preserved: true,
  fingerprint: "aGVsbG8=:deadbeef",
};

describe("QuarantinePage", () => {
  it("lists quarantined records", () => {
    render(
      <QuarantinePage
        records={[record]}
        tenantId="default-tenant"
        onReplay={vi.fn()}
        onReEvaluate={vi.fn()}
        onFilter={vi.fn()}
        reload={vi.fn()}
      />,
    );
    expect(screen.getByTestId("dlq-list")).toBeInTheDocument();
    expect(screen.getByText("DLQ-1")).toBeInTheDocument();
    expect(screen.getByText("parse-failure")).toBeInTheDocument();
  });

  it("replays a record and shows the preserved payload", async () => {
    const onReplay = vi.fn(async () => "bW9jaw==");
    render(
      <QuarantinePage
        records={[record]}
        tenantId="default-tenant"
        onReplay={onReplay}
        onReEvaluate={vi.fn()}
        onFilter={vi.fn()}
        reload={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("replay-DLQ-1"));
    await waitFor(() => expect(onReplay).toHaveBeenCalledWith("DLQ-1"));
    expect(await screen.findByTestId("dlq-payload")).toHaveTextContent("bW9jaw==");
  });

  it("re-evaluates and tells the parent", async () => {
    const onReEvaluate = vi.fn(async () => undefined);
    render(
      <QuarantinePage
        records={[record]}
        tenantId="default-tenant"
        onReplay={vi.fn()}
        onReEvaluate={onReEvaluate}
        onFilter={vi.fn()}
        reload={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("reeval-DLQ-1"));
    await waitFor(() => expect(onReEvaluate).toHaveBeenCalledWith("DLQ-1"));
  });
});