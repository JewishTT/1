import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { GeospatialWorkspace } from "./GeospatialWorkspace";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("GeospatialWorkspace", () => {
  it("embeds only the explicitly configured spatial service", () => {
    vi.stubEnv("VITE_GEV_EMBED_URL", "http://127.0.0.1:14173");

    render(<GeospatialWorkspace />);

    const frame = screen.getByTestId("geospatial-frame");
    expect(frame).toHaveAttribute("src", "http://127.0.0.1:14173/?embed=1");
    expect(frame).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin allow-pointer-lock");
    expect(frame).toHaveAttribute("allow", "fullscreen");
  });

  it("does not render a remote HTTP service", () => {
    vi.stubEnv("VITE_GEV_EMBED_URL", "http://spatial.example.net");

    render(<GeospatialWorkspace />);

    expect(screen.queryByTestId("geospatial-frame")).not.toBeInTheDocument();
    expect(screen.getByTestId("geospatial-unconfigured")).toBeInTheDocument();
  });

  it("refuses a same-origin URL so the sandbox cannot be escaped", () => {
    vi.stubEnv("VITE_GEV_EMBED_URL", window.location.origin);

    render(<GeospatialWorkspace />);

    expect(screen.queryByTestId("geospatial-frame")).not.toBeInTheDocument();
    expect(screen.getByTestId("geospatial-unconfigured")).toBeInTheDocument();
  });

  it("keeps the optional service offline when no URL is configured", () => {
    vi.stubEnv("VITE_GEV_EMBED_URL", "");

    render(<GeospatialWorkspace />);

    expect(screen.queryByTestId("geospatial-frame")).not.toBeInTheDocument();
    expect(screen.getByTestId("geospatial-unconfigured")).toBeInTheDocument();
  });
});
