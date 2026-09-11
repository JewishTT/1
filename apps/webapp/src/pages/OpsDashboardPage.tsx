export interface OpsMetrics {
  throughput_per_s: number;
  useful_observations: number;
  discovery_yield: number;
  duplicate_ratio: number;
  browser_utilization: number;
  lags_s: Record<string, number>;
  queues: Record<string, number>;
  storage_growth_b: Record<string, number>;
  cost_per_1m_obs: number;
  pools?: Record<string, { healthy: boolean; active: number; capacity: number; failures: number }>;
}

interface Props {
  metrics: OpsMetrics;
  onRefresh?: () => void;
}

function fmt(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)} GB`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} MB`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)} kB`;
  return `${n} B`;
}

function Tile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="op-tile" data-testid={`op-${label}`}>
      <span className="op-label">{label}</span>
      <span className="op-value">{typeof value === "number" ? value.toLocaleString() : value}</span>
    </div>
  );
}

export function OpsDashboardPage({ metrics, onRefresh }: Props) {
  const lagEntries = Object.entries(metrics.lags_s);
  const queueEntries = Object.entries(metrics.queues);
  const storageEntries = Object.entries(metrics.storage_growth_b);
  const poolEntries = Object.entries(metrics.pools ?? {});

  return (
    <section data-testid="ops-dashboard">
      <h1>Operations dashboard</h1>
      <button type="button" data-testid="refresh-btn" onClick={onRefresh}>
        Refresh
      </button>

      <div className="panel">
        <h2>Throughput & knowledge</h2>
        <div className="tiles">
          <Tile label="throughput" value={metrics.throughput_per_s} />
          <Tile label="useful obs" value={metrics.useful_observations} />
          <Tile label="discovery yield" value={`${(metrics.discovery_yield * 100).toFixed(0)}%`} />
          <Tile label="duplicate ratio" value={`${(metrics.duplicate_ratio * 100).toFixed(0)}%`} />
        </div>
      </div>

      <div className="panel">
        <h2>Cost & utilization</h2>
        <div className="tiles">
          <Tile label="cost / 1M obs" value={`$${metrics.cost_per_1m_obs}`} />
          <Tile label="browser util" value={`${(metrics.browser_utilization * 100).toFixed(0)}%`} />
        </div>
      </div>

      <div className="panel">
        <h2>Lags (freshness-lag)</h2>
        {lagEntries.length === 0 ? (
          <p>No lags.</p>
        ) : (
          <ul data-testid="lags">
            {lagEntries.map(([k, v]) => (
              <li key={k} data-testid="lag">
                {k}: {v.toFixed(1)}s
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel">
        <h2>Queues (queue-age)</h2>
        {queueEntries.length === 0 ? (
          <p>No queues.</p>
        ) : (
          <ul data-testid="queues">
            {queueEntries.map(([k, v]) => (
              <li key={k}>
                {k}: {v.toLocaleString()}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel">
        <h2>Storage growth (projection-lag)</h2>
        {storageEntries.length === 0 ? (
          <p>No storage stats.</p>
        ) : (
          <ul data-testid="storage">
            {storageEntries.map(([k, v]) => (
              <li key={k}>
                {k}: {fmt(v)}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel">
        <h2>Worker pools</h2>
        {poolEntries.length === 0 ? (
          <p>No pool data.</p>
        ) : (
          <ul data-testid="pools">
            {poolEntries.map(([name, p]) => (
              <li key={name} data-testid="pool" data-healthy={p.healthy}>
                {name}: {p.healthy ? "healthy" : "UNHEALTHY"} ({p.active}/{p.capacity}, {p.failures}{" "}
                failures)
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
