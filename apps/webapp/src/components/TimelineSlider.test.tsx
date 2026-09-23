import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TimelineSlider } from "./TimelineSlider";

const ONSCRUB = vi.fn();

describe("TimelineSlider", () => {
  beforeEach(() => {
    ONSCRUB.mockClear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the range input, play button and counts at T", () => {
    render(
      <TimelineSlider
        min={0}
        max={6000}
        value={1500}
        counts={{ nodes: 2, edges: 1 }}
        onScrub={ONSCRUB}
      />,
    );
    expect(screen.getByTestId("timelapse-slider")).toBeInTheDocument();
    expect(screen.getByTestId("timelapse-range")).toHaveValue("1500");
    expect(screen.getByTestId("timelapse-play")).toHaveAccessibleName("play timelapse");
    expect(screen.getByTestId("timelapse-counts")).toHaveTextContent("N 2 · E 1");
  });

  it("emits T on scrub", () => {
    render(<TimelineSlider min={0} max={6000} value={0} onScrub={ONSCRUB} />);
    fireEvent.change(screen.getByTestId("timelapse-range"), { target: { value: "3000" } });
    expect(ONSCRUB).toHaveBeenCalledWith(3000);
  });

  it("runs a deterministic play sequence to the window end", () => {
    render(
      <TimelineSlider min={0} max={3000} value={0} onScrub={ONSCRUB} ticks={[1000, 2000, 3000]} />,
    );
    fireEvent.click(screen.getByTestId("timelapse-play"));
    expect(screen.getByTestId("timelapse-play")).toHaveAccessibleName("pause timelapse");

    act(() => vi.advanceTimersByTime(1200));
    const calls = ONSCRUB.mock.calls.map((c) => c[0] as number);
    expect(calls.length).toBeGreaterThan(1);
    expect(calls.every((t) => t > 0 && t <= 3000)).toBe(true);
    expect(calls).toEqual([...calls].sort((a, b) => a - b));

    act(() => vi.advanceTimersByTime(60000));
    expect(ONSCRUB.mock.calls.at(-1)![0]).toBe(3000);
    expect(screen.getByTestId("timelapse-play")).toHaveAccessibleName("play timelapse");
  });

  it("does not step past max while playing", () => {
    render(<TimelineSlider min={0} max={300} value={280} onScrub={ONSCRUB} />);
    fireEvent.click(screen.getByTestId("timelapse-play"));
    act(() => vi.advanceTimersByTime(1000));
    expect(ONSCRUB.mock.calls.every((c) => (c[0] as number) <= 300)).toBe(true);
  });

  it("renders an honest empty state for a closed window", () => {
    render(
      <TimelineSlider
        min={1000}
        max={1000}
        value={1000}
        counts={{ nodes: 0, edges: 0 }}
        onScrub={ONSCRUB}
      />,
    );
    expect(screen.getByTestId("timelapse-play")).toBeDisabled();
    expect(screen.getByTestId("timelapse-range")).toBeDisabled();
  });
});