import styles from "./GeospatialContext.module.css";

const RAW_EMBED_URL = (import.meta.env.VITE_GEV_EMBED_URL ?? "").trim();

function resolveEmbedUrl(raw: string): string | null {
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    url.searchParams.set("embed", "1");
    return url.toString();
  } catch {
    return null;
  }
}

const EMBED_URL = resolveEmbedUrl(RAW_EMBED_URL);

export function GeospatialContext() {
  return (
    <main className={styles.page} data-testid="geospatial-context-page">
      <header className={styles.header}>
        <div>
          <div className={styles.kicker}>SPATIAL CONTEXT / PUBLIC DATA</div>
          <h1>Geospatial Context</h1>
          <p>
            Independent situational context for environmental events, public infrastructure
            and space activity. This workspace is deliberately detached from person dossiers
            and investigation identifiers.
          </p>
        </div>
        <span className={styles.status}>OPTIONAL SERVICE</span>
      </header>

      <section className={styles.boundary} aria-label="Geospatial workspace boundary">
        <strong>Context boundary</strong>
        <span>
          No person, case or entity identifiers are sent to the map service. Camera, ALPR,
          biometric, voice and person-tracking capabilities are not exposed here.
        </span>
      </section>

      {EMBED_URL ? (
        <section className={styles.frameShell} aria-label="Geospatial map">
          <iframe
            className={styles.frame}
            src={EMBED_URL}
            title="Independent public geospatial context map"
            loading="lazy"
            referrerPolicy="no-referrer"
            sandbox="allow-scripts allow-same-origin"
            allow="fullscreen"
            data-testid="geospatial-context-frame"
          />
        </section>
      ) : (
        <section className={styles.unconfigured} data-testid="geospatial-context-unconfigured">
          <div className={styles.emptyCode}>GEOSPATIAL SERVICE / NOT CONFIGURED</div>
          <h2>Spatial context is not connected</h2>
          <p>
            Start the optional local service and set <code>VITE_GEV_EMBED_URL</code> to its
            loopback URL. The main acquisition and investigation pipelines do not depend on it.
          </p>
          <pre>{'./scripts/checkout-geospatial-upstream.sh\n# then start the geospatial compose profile'}</pre>
        </section>
      )}
    </main>
  );
}
