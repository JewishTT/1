import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { applyInitialAppearanceAttributes } from "./workspace/useAppearance";
// One stylesheet entry (§62): layers.css aggregates tokens → base → components
// → shell → workspace → utilities → legacy → donor sheets. index.css is
// imported *by* layers.css, so it must not also be imported here.
import "./styles/layers.css";

const queryClient = new QueryClient();

// FR-103, before the first paint rather than after it. `data-density` and
// `data-theme` select which token blocks the cascade applies, so writing them
// in an effect would mean the shell first renders at the default density and
// then reflows to the stored one — a layout shift caused by the app rather than
// by the data. The AppShell effect keeps them in step from then on.
applyInitialAppearanceAttributes();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
