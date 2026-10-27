import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { Modal } from "./Modal";

function ModalHarness() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open modal</button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Confirm acquisition"
        testId="confirm-modal"
        description="Review the scope before submitting the task."
        actions={<button type="button">Confirm action</button>}
      >
        <button type="button">First action</button>
      </Modal>
    </>
  );
}

describe("Modal", () => {
  it("names the dialog, traps Tab and restores focus after Escape", () => {
    render(<ModalHarness />);
    const trigger = screen.getByRole("button", { name: "Open modal" });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Confirm acquisition" });
    const close = withinButton(dialog, "Close dialog");
    const confirm = withinButton(dialog, "Confirm action");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleDescription("Review the scope before submitting the task.");
    expect(close).toHaveFocus();

    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();
    fireEvent.keyDown(confirm, { key: "Tab" });
    expect(close).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Confirm acquisition" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).toBe("");
  });

  it("closes from the backdrop when configured to do so", () => {
    render(<ModalHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Open modal" }));
    fireEvent.mouseDown(screen.getByTestId("confirm-modal-scrim"));
    expect(screen.queryByRole("dialog", { name: "Confirm acquisition" })).not.toBeInTheDocument();
  });
});

function withinButton(root: HTMLElement, name: string): HTMLButtonElement {
  const button = root.querySelector<HTMLButtonElement>(`button[aria-label="${name}"]`)
    ?? Array.from(root.querySelectorAll<HTMLButtonElement>("button")).find((candidate) => candidate.textContent?.includes(name));
  if (!button) throw new Error(`Missing button: ${name}`);
  return button;
}
