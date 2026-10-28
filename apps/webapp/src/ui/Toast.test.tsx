import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Toast } from "./Toast";
import { ToastViewport } from "./ToastViewport";

describe("Toast", () => {
  it("announces ordinary notifications politely and exposes dismissal", () => {
    const onDismiss = vi.fn();
    render(
      <Toast
        tone="success"
        title="Export ready"
        message="The demo export is ready to review."
        onDismiss={onDismiss}
      />,
    );

    const toast = screen.getByRole("status");
    expect(toast).toHaveAttribute("aria-live", "polite");
    expect(toast).toHaveAttribute("data-tone", "success");
    expect(screen.getByText("Export ready")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss notification" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("provides a named region for a fixed stack of notifications", () => {
    render(
      <ToastViewport testId="toast-viewport">
        <Toast message="Export complete." tone="success" />
        <Toast message="One source is unavailable." tone="warning" />
      </ToastViewport>,
    );

    expect(screen.getByRole("region", { name: "Notifications" })).toHaveAttribute("data-testid", "toast-viewport");
    expect(screen.getAllByRole("status")).toHaveLength(2);
  });

  it("announces genuine danger notifications assertively", () => {
    render(<Toast tone="danger" message="Source gateway failed." />);
    expect(screen.getByRole("alert")).toHaveAttribute("aria-live", "assertive");
  });
});
