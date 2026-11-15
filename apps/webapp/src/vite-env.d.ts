/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GEV_EMBED_URL?: string;
}

// Vite supplies import.meta.env.DEV for gating development-only visual fixtures.
