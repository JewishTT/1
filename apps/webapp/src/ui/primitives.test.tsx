import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { Badge, StatusDot } from "./Badge";
import { Button, IconButton } from "./Button";
import { DataTable } from "./DataTable";
import { EmptyState, Skeleton } from "./Feedback";
import { Input, Select } from "./Input";
import { Drawer, Popover, Tooltip } from "./Overlay";
import { Tabs } from "./Tabs";
import { WORK_STATUSES, statusTone, toWorkStatus } from "./status";

/**
 * Primitive tests (§60, §67, §92). Deliberately about *behaviour and
 * accessibility*, not about class names — a stylesheet detail should never be
 * able to fail a test, and a semantic contract should always be able to.
 */

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("§92 — the status vocabulary is closed", () => {
  it("is exactly the eight documented states", () => {
    expect([...WORK_STATUSES]).toEqual([
      "Healthy",
      "Running",
      "Queued",
      "Paused",
      "Completed",
      "Failed",
      "Blocked",
      "Unknown",
    ]);
  });

  it("maps backend spellings onto it and collapses everything else to Unknown", () => {
    expect(toWorkStatus("ACTIVE")).toBe("Healthy");
    expect(toWorkStatus("running")).toBe("Running");
    expect(toWorkStatus("PENDING")).toBe("Queued");
    expect(toWorkStatus("REJECTED")).toBe("Blocked");
    expect(toWorkStatus("DISABLED")).toBe("Blocked");
    expect(toWorkStatus(null)).toBe("Unknown");
    expect(toWorkStatus("WHAT_IS_THIS")).toBe("Unknown");
    expect(toWorkStatus("")).toBe("Unknown");
  });

  it("gives every state a tone, so no state can be rendered colourless", () => {
    for (const status of WORK_STATUSES) {
      expect(statusTone(status), status).toBeTypeOf("string");
    }
  });

  it("puts red only on the states that mean something is wrong", () => {
    expect(statusTone("Failed")).toBe("danger");
    expect(statusTone("Blocked")).toBe("danger");
    expect(statusTone("Paused")).toBe("gold");
    expect(statusTone("Completed")).toBe("strong");
    expect(statusTone("Queued")).toBe("steel");
    expect(statusTone("Unknown")).toBe("dim");
  });
});

describe("StatusDot — colour never carries meaning alone", () => {
  it("exposes the state as text for assistive tech even without a visible label", () => {
    render(<StatusDot status="Running" />);
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("renders no live treatment when the caller did not ask for one", () => {
    const { container } = render(<StatusDot status="Running" />);
    expect(container.querySelector(".ui-status-dot")).not.toHaveAttribute("data-live");
  });

  it("marks the dot decorative so it is not announced twice", () => {
    const { container } = render(<StatusDot status="Failed" label="FAILED" />);
    expect(container.querySelector(".ui-status-dot")).toHaveAttribute("aria-hidden", "true");
  });

  it("only asks for the live treatment when work is actually running", () => {
    const running = render(<StatusDot status="Running" live />);
    expect(running.container.querySelector(".ui-status-dot")).toHaveAttribute("data-live", "true");

    const paused = render(<StatusDot status="Paused" live />);
    expect(paused.container.querySelector(".ui-status-dot")).not.toHaveAttribute("data-live");
  });
});

describe("Button / IconButton", () => {
  it("defaults to type=button so it cannot submit a form by accident", () => {
    render(<Button>Go</Button>);
    expect(screen.getByRole("button", { name: "Go" })).toHaveAttribute("type", "button");
  });

  it("honours an explicit type", () => {
    render(<Button type="submit">Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("type", "submit");
  });

  it("fires onClick", () => {
    const clicks: number[] = [];
    render(<Button onClick={() => clicks.push(1)}>Go</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(clicks).toHaveLength(1);
  });

  it("does not fire when disabled", () => {
    let fired = false;
    render(
      <Button disabled onClick={() => (fired = true)}>
        Go
      </Button>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(fired).toBe(false);
  });

  it("gives an icon-only button an accessible name (§67)", () => {
    render(<IconButton icon="close" label="Clear selection" />);
    expect(screen.getByRole("button", { name: "Clear selection" })).toBeInTheDocument();
  });

  it("reports pressed state when used as a toggle", () => {
    render(<IconButton icon="panel-left" label="Toggle rail" aria-pressed />);
    expect(screen.getByRole("button", { name: "Toggle rail" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("Input / Select", () => {
  it("associates the visible label with the control", () => {
    render(<Input id="q" label="Evidence query" />);
    expect(screen.getByLabelText("Evidence query")).toBeInTheDocument();
  });

  it("forwards a ref to the underlying control, so the palette can focus it", () => {
    // The forwardRef contract: a parent that focuses the ref focuses the input,
    // which is what ⌘K → type → Enter depends on.
    let captured: HTMLInputElement | null = null;
    render(<Input id="ref-target" label="Focusable" ref={(node) => (captured = node)} />);
    expect(captured).toBe(screen.getByLabelText("Focusable"));
    expect(captured).toBeInstanceOf(HTMLInputElement);
  });

  it("calls onValueChange with the option value", () => {
    const seen: string[] = [];
    render(
      <Select
        label="Object kind"
        value="all"
        onValueChange={(value) => seen.push(value)}
        options={[
          { value: "all", label: "All" },
          { value: "Entity", label: "Entity" },
        ]}
      />,
    );
    fireEvent.change(screen.getByLabelText("Object kind"), { target: { value: "Entity" } });
    expect(seen).toEqual(["Entity"]);
  });

  it("is controlled: it renders the value it is given", () => {
    render(
      <Select
        label="Kind"
        value="Entity"
        onValueChange={() => {}}
        options={[
          { value: "all", label: "All" },
          { value: "Entity", label: "Entity" },
        ]}
      />,
    );
    expect(screen.getByLabelText("Kind")).toHaveValue("Entity");
  });
});

describe("Tabs — WAI-ARIA keyboard model", () => {
  const items = [
    { value: "overview", label: "Overview" },
    { value: "graph", label: "Graph" },
    { value: "objects", label: "Objects" },
  ];

  it("labels the tablist and marks the active tab", () => {
    render(<Tabs items={items} value="graph" onValueChange={() => {}} label="Workspace views" />);
    expect(screen.getByRole("tablist", { name: "Workspace views" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Graph" })).toHaveAttribute("aria-selected", "true");
  });

  it("uses a roving tabindex", () => {
    render(<Tabs items={items} value="graph" onValueChange={() => {}} label="Views" />);
    expect(screen.getByRole("tab", { name: "Graph" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("tabindex", "-1");
  });

  it("moves selection on click", () => {
    const seen: string[] = [];
    render(<Tabs items={items} value="overview" onValueChange={(v) => seen.push(v)} label="Views" />);
    fireEvent.click(screen.getByRole("tab", { name: "Objects" }));
    expect(seen).toEqual(["objects"]);
  });

  it("moves focus with the arrow keys in bar orientation", () => {
    render(<Tabs items={items} value="overview" onValueChange={() => {}} label="Views" orientation="bar" />);
    const first = screen.getByRole("tab", { name: "Overview" });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Graph" }));
  });

  it("wraps around at the ends", () => {
    render(<Tabs items={items} value="graph" onValueChange={() => {}} label="Views" orientation="bar" />);
    const active = screen.getByRole("tab", { name: "Graph" });
    active.focus();
    fireEvent.keyDown(active, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Overview" }));
  });

  it("uses Up/Down in rail orientation", () => {
    render(<Tabs items={items} value="overview" onValueChange={() => {}} label="Rail" orientation="rail" />);
    const first = screen.getByRole("tab", { name: "Overview" });
    first.focus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Graph" }));
  });

  it("jumps to the ends with Home and End", () => {
    render(<Tabs items={items} value="graph" onValueChange={() => {}} label="Views" />);
    const active = screen.getByRole("tab", { name: "Graph" });
    active.focus();
    fireEvent.keyDown(active, { key: "End" });
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Objects" }));
    fireEvent.keyDown(active, { key: "Home" });
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Overview" }));
  });
});

describe("Tooltip / Popover / Drawer", () => {
  it("describes its trigger and hides the content until hovered", () => {
    render(
      <Tooltip content="Resize the rail">
        <button type="button">handle</button>
      </Tooltip>,
    );
    const tooltip = screen.getByRole("tooltip", { hidden: true });
    expect(tooltip).toHaveAttribute("hidden");
    expect(tooltip).toHaveTextContent("Resize the rail");
  });

  it("gives the popover trigger its expanded state", () => {
    render(
      <Popover label="Appearance" trigger={<button type="button">density</button>}>
        <span>menu</span>
      </Popover>,
    );
    expect(screen.getByRole("button", { name: "density" })).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(screen.getByRole("button", { name: "density" }));
    expect(screen.getByRole("button", { name: "density" })).toHaveAttribute("aria-expanded", "true");
  });

  it("does not render a drawer when closed, and labels it when open", () => {
    const { rerender } = render(
      <Drawer open={false} onClose={() => {}} label="Activity">
        <span>events</span>
      </Drawer>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    rerender(
      <Drawer open onClose={() => {}} label="Activity">
        <span>events</span>
      </Drawer>,
    );
    expect(screen.getByRole("dialog", { name: "Activity" })).toBeInTheDocument();
  });

  it("closes on Escape", () => {
    let closes = 0;
    render(
      <Drawer open onClose={() => (closes += 1)} label="Activity">
        <span>events</span>
      </Drawer>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(closes).toBe(1);
  });

  it("closes on scrim click", () => {
    let closes = 0;
    render(
      <Drawer open onClose={() => (closes += 1)} label="Activity" testId="drawer">
        <span>events</span>
      </Drawer>,
    );
    fireEvent.click(screen.getByTestId("drawer-scrim"));
    expect(closes).toBe(1);
  });
});

describe("EmptyState / Skeleton", () => {
  it("states the absence and offers the next step (§69)", () => {
    render(
      <EmptyState
        title="Nothing selected"
        description="Select an entity to continue."
        action={<Button>Select first</Button>}
      />,
    );
    expect(screen.getByText("Nothing selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select first" })).toBeInTheDocument();
  });

  it("announces loading once, not once per placeholder row", () => {
    render(<Skeleton rows={5} label="Loading object details" />);
    expect(screen.getByText("Loading object details")).toBeInTheDocument();
  });

  it("marks the region busy", () => {
    const { container } = render(<Skeleton rows={2} label="Loading" />);
    expect(container.querySelector(".ui-skeleton")).toHaveAttribute("aria-busy", "true");
  });
});

describe("DataTable — shell semantics", () => {
  const rows = [
    { id: "OBS-1", uri: "https://a", status: "Running" },
    { id: "OBS-2", uri: "https://b", status: "Failed" },
  ];
  const columns = [
    { key: "id", header: "Observation", mono: true, render: (row: (typeof rows)[number]) => row.id },
    { key: "uri", header: "URI", render: (row: (typeof rows)[number]) => row.uri },
  ];

  it("renders a captioned table", () => {
    render(<DataTable caption="Observations" columns={columns} rows={rows} rowId={(row) => row.id} />);
    expect(screen.getByRole("table", { name: "Observations" })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2
  });

  it("marks the globally selected row", () => {
    render(
      <DataTable
        caption="Observations"
        columns={columns}
        rows={rows}
        rowId={(row) => row.id}
        selectedId="OBS-2"
      />,
    );
    expect(screen.getByTestId("row-OBS-2")).toHaveAttribute("data-selected", "true");
    expect(screen.getByTestId("row-OBS-1")).toHaveAttribute("data-selected", "false");
  });

  it("activates a row by click and by keyboard (§67)", () => {
    const picked: string[] = [];
    render(
      <DataTable
        caption="Observations"
        columns={columns}
        rows={rows}
        rowId={(row) => row.id}
        onRowSelect={(id) => picked.push(id)}
      />,
    );
    fireEvent.click(screen.getByTestId("row-OBS-1"));
    fireEvent.keyDown(screen.getByTestId("row-OBS-2"), { key: "Enter" });
    expect(picked).toEqual(["OBS-1", "OBS-2"]);
  });

  it("renders the empty state instead of an empty table", () => {
    render(
      <DataTable
        caption="Observations"
        columns={columns}
        rows={[]}
        rowId={(row) => row.id}
        emptyState={<EmptyState title="No observations" />}
      />,
    );
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("No observations")).toBeInTheDocument();
  });

  it("is not focusable when rows are not selectable", () => {
    render(<DataTable caption="Observations" columns={columns} rows={rows} rowId={(row) => row.id} />);
    expect(screen.getByTestId("row-OBS-1")).not.toHaveAttribute("tabindex");
  });
});

describe("Badge", () => {
  it("marks classification badges as such, so gold never reads as a warning", () => {
    render(<Badge role="classification" tone="gold">observation</Badge>);
    expect(screen.getByText("observation")).toHaveAttribute("data-role", "classification");
  });
});