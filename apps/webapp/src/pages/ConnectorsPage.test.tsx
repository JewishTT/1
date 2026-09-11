import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Connector, ReconPlan } from "../lib/api";
import { ConnectorsPage } from "./ConnectorsPage";

const connector: Connector = {
  connector_id: "CN-abc123",
  name: "subdomains-http",
  tenant_id: "default-tenant",
  source_types: ["HTTP"],
  capabilities: {},
  policy_id: "policies/default",
  version: "1.0",
  status: "REGISTERED",
  contract_compliant: true,
};

const plan: ReconPlan = {
  plan_id: "RP-1",
  investigation_id: "INV-7",
  tenant_id: "default-tenant",
  strategy: { connector: "subdomains-http" },
  task_ids: [],
  status: "PLANNED",
  started_at: "",
  finished_at: "",
};

describe("ConnectorsPage", () => {
  it("lists connectors with status and plans", () => {
    render(
      <ConnectorsPage
        connectors={[connector]}
        plans={[plan]}
        register={vi.fn()}
        activate={vi.fn()}
        createPlan={vi.fn()}
        reload={vi.fn()}
      />,
    );
    expect(screen.getByTestId("connector-list")).toBeInTheDocument();
    expect(screen.getByText("subdomains-http")).toBeInTheDocument();
    expect(screen.getByTestId("plan-list")).toBeInTheDocument();
    expect(screen.getByText("RP-1")).toBeInTheDocument();
  });

  it("registers a connector through the callback", async () => {
    const register = vi.fn(async () => undefined);
    const { container } = render(
      <ConnectorsPage
        connectors={[]}
        plans={[]}
        register={register}
        activate={vi.fn()}
        createPlan={vi.fn()}
        reload={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByTestId("conn-name"), { target: { value: "cert-scan" } });
    fireEvent.change(screen.getByTestId("conn-sources"), { target: { value: "DNS, SSL" } });
    fireEvent.submit(container.querySelector('[data-testid="register-form"]')!);
    await waitFor(() =>
      expect(register).toHaveBeenCalledWith({ name: "cert-scan", source_types: ["DNS", "SSL"] }),
    );
  });

  it("activates a registered connector", async () => {
    const activate = vi.fn(async () => undefined);
    render(
      <ConnectorsPage
        connectors={[connector]}
        plans={[]}
        register={vi.fn()}
        activate={activate}
        createPlan={vi.fn()}
        reload={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("activate-subdomains-http"));
    await waitFor(() => expect(activate).toHaveBeenCalledWith("subdomains-http"));
  });
});