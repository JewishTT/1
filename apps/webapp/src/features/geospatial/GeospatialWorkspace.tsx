import styles from "./GeospatialWorkspace.module.css";

/**
 * Public geospatial context, isolated from person/research-case identifiers.
 *
 * This is an optional external workspace. Its URL comes only from an explicit
 * deployment setting; it is never built from the current route, entity
 * selection, investigation, or search query.
 */
function resolveEmbedUrl(raw: string | undefined): string | null {
  const candidate = raw?.trim();
  if (!candidate) return null;

  try {
    const url = new URL(candidate);
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
    // `allow-scripts` + `allow-same-origin` is only safe when the embedded
    // document is a distinct origin; otherwise it can remove its own sandbox.
    if (typeof window !== "undefined" && url.origin === window.location.origin) return null;
    const loopback = ["localhost", "127.0.0.1", "[::1]", "::1"].includes(url.hostname);
    if (url.protocol === "http:" && !loopback) return null;
    url.searchParams.set("embed", "1");
    return url.toString();
  } catch {
    return null;
  }
}

const EMBED_URL = resolveEmbedUrl(import.meta.env.VITE_GEV_EMBED_URL);

export function GeospatialWorkspace() {
  return (
    <main className={styles.page} data-testid="geospatial-workspace">
      <header className={styles.header}>
        <div>
          <p className={styles.kicker}>PUBLIC CONTEXT / GEOINT</p>
          <h1>Spatial context</h1>
          <p className={styles.description}>
            Environmental events, infrastructure and space layers from public sources.
            This workspace is separate from person and case research.
          </p>
        </div>
        <span className={styles.scope}>NO PERSON CONTEXT</span>
      </header>

      {EMBED_URL ? (
        <section className={styles.frameShell} aria-label="God's Eye View spatial workspace">
          <iframe
            className={styles.frame}
            src={EMBED_URL}
            title="God's Eye View — public spatial context"
            loading="lazy"
            referrerPolicy="no-referrer"
            sandbox="allow-scripts allow-same-origin allow-pointer-lock"
            allow="fullscreen"
            data-testid="geospatial-frame"
          />
        </section>
      ) : (
        <section className={styles.setup} data-testid="geospatial-unconfigured">
          <span className={styles.setupCode}>SPATIAL SERVICE / NOT CONFIGURED</span>
          <h2>Optional geospatial service is offline</h2>
          <p>
            Initialize the pinned God's Eye View submodule and start the isolated
            <code> geospatial </code> Compose profile. Then set
            <code> VITE_GEV_EMBED_URL </code> to the service origin, for example
            <code> http://127.0.0.1:14173 </code>.
          </p>
          <p>
            The service is deliberately not bundled into the core application and
            receives no identifiers or evidence from this workspace.
          </p>
        </section>
      )}
    </main>
  );
}
