import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, InvestigationView } from "../lib/api";

export function InvestigationListContainer() {
  const [items, setItems] = useState<InvestigationView[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try { setItems((await api.listInvestigations()).investigations); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const create = async () => {
    if (!name.trim()) return;
    try { await api.createInvestigation({ name: name.trim() }); setName(""); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  };
  return <section data-testid="investigations-page">
    <h1>Investigations</h1>
    <div className="panel"><h2>New investigation</h2><input data-testid="new-investigation-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="investigation name" /><button type="button" className="btn btn-primary btn-sm" onClick={() => void create()}>Create</button></div>
    {error && <p data-testid="error-view">{error}</p>}
    {loading ? <p>Loading…</p> : items.length === 0 ? <p data-testid="investigations-empty">No investigations yet. Create one above.</p> : <ul>{items.map((item) => <li key={item.investigation_id}><Link to={`/investigations/${item.investigation_id}`}>{item.name}</Link> · {item.state}</li>)}</ul>}
  </section>;
}
