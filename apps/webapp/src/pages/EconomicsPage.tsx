import { OpsMetrics } from "../lib/api";

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
    <div className="op-tile" data-testid={`eco-${label}`}>
      <span className="op-label">{label}</span>
      <span className="op-value">{typeof value === "number" ? value.toLocaleString() : value}</span>
    </div>
  );
}

export function EconomicsPage({ metrics, onRefresh }: Props) {
  const lagEntries = Object.entries(metrics.lags_s);
  const queueEntries = Object.entries(metrics.queues);
  const storageEntries = Object.entries(metrics.storage_growth_b);
  const poolEntries = Object.entries(metrics.pools ?? {});
  const runningBudget = (metrics.cost_per_1m_obs * metrics.useful_observations) / 1_000_000;
  const waste = metrics.useful_observations * metrics.duplicate_ratio;

  return (
    <section className="command-page economics-page" data-testid="economic-dashboard">
      <div className="page-banner">
        <div>
          <span className="op-label">ECON / RESOURCE INTELLIGENCE</span>
          <h1>Intelligence economy</h1>
          <p className="panel-note">Cost, yield and worker capacity across the evidence pipeline.</p>
        </div>
        <span className="status-chip status-chip-live">LEDGER LINKED</span>
      </div>

      <div className="tiles command-metrics">
        <Tile label="cost / 1M obs" value={`$${metrics.cost_per_1m_obs.toFixed(2)}`} />
        <Tile label="running budget" value={`$${runningBudget.toFixed(2)}`} />
        <Tile label="duplicate waste (obs)" value={waste.toLocaleString()} />
        <Tile label="discovery yield" value={`${(metrics.discovery_yield * 100).toFixed(0)}%`} />
      </div>

      <div className="panel command-panel">
        <h2>Throughput economics</h2>
        <div className="tiles">
          <Tile label="throughput / s" value={metrics.throughput_per_s} />
          <Tile label="useful observations" value={metrics.useful_observations} />
          <Tile label="browser utilization" value={`${(metrics.browser_utilization * 100).toFixed(0)}%`} />
        </div>
      </div>

      <div className="panel command-panel">
        <h2>Storage growth (projection-lag)</h2>
        {storageEntries.length === 0 ? (
          <p className="panel-note">No storage stats.</p>
        ) : (
          <ul data-testid="eco-storage">
            {storageEntries.map(([k, v]) => (
              <li key={k} className="insp-row">
                <b>{k}:</b> {fmt(v)}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel command-panel">
        <h2>Pipeline latency</h2>
        {lagEntries.length === 0 ? (
          <p className="panel-note">No lags.</p>
        ) : (
          <ul data-testid="eco-lags">
            {lagEntries.map(([k, v]) => (
              <li key={k} className="insp-row">
                <b>{k}:</b> {v.toFixed(1)}s
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel command-panel">
        <h2>Queue load</h2>
        {queueEntries.length === 0 ? (
          <p className="panel-note">No queues.</p>
        ) : (
          <ul data-testid="eco-queues">
            {queueEntries.map(([k, v]) => (
              <li key={k} className="insp-row">
                <b>{k}:</b> {v.toLocaleString()}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel command-panel">
        <h2>Worker pool CAPEX / OPEX</h2>
        {poolEntries.length === 0 ? (
          <p className="panel-note">No pool data.</p>
        ) : (
          <table className="dlq-table" data-testid="eco-pools">
            <thead>
              <tr>
                <th>pool</th>
                <th>state</th>
                <th>active/capacity</th>
                <th>failures</th>
              </tr>
            </thead>
            <tbody>
              {poolEntries.map(([name, p]) => (
                <tr key={name} data-testid="eco-pool" data-healthy={p.healthy}>
                  <td>{name}</td>
                  <td>
                    <span className="status-chip">{p.healthy ? "HEALTHY" : "UNHEALTHY"}</span>
                  </td>
                  <td>
                    {p.active}/{p.capacity}
                  </td>
                  <td>{p.failures}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="panel-actions">
          <button type="button" className="btn btn-sm" onClick={onRefresh} data-testid="eco-refresh">
            ↻ REFRESH LEDGER
          </button>
        </div>
      </div>
    </section>
  );
}