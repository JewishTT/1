export type NetStatus<T> =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "done"; data: T };

export function NetResult<T>({ status }: { status: NetStatus<T> }) {
  switch (status.state) {
    case "idle":
      return <p className="panel-note">Not run yet.</p>;
    case "loading":
      return <p className="panel-note">Analyzing…</p>;
    case "error":
      return <p className="panel-note" style={{ color: "var(--c-danger)" }}>{status.message}</p>;
    case "done":
      return null;
  }
}