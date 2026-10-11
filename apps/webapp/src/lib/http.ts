/**
 * The one place this app talks HTTP.
 *
 * There were four copies of the same ten lines — `lib/api.ts`, `lib/science/api.ts` (twice,
 * once for a `/api/science` base and once for a `/api/v1/network` base) and
 * `lib/dossier/api.ts` — and they had already drifted into three different error contracts.
 * A caller that handled `err.detail` correctly against one client saw `"[object Object]"`
 * through another, and a fourth page fetched with a bare `fetch` and returned `{ok: false}`
 * instead of throwing, so its failure was invisible to the container that owns error
 * rendering.
 *
 * Every copy also carried the same dead line: `headers` were merged *before* `...init`, so a
 * caller passing its own `init.headers` overwrote the whole merge and silently lost
 * `Content-Type`. It read like a feature and was the opposite of one.
 *
 * What this module does not do is know about any endpoint. Base paths stay with their
 * clients, because `/api/science` and `/api/v1` are different surfaces, not different
 * vocabularies for one.
 */

/**
 * A failed request, carrying enough of the response to be actionable.
 *
 * `message` stays a plain string so every existing `err.message` handler keeps working, but
 * `status` and `detail` are now reachable without re-parsing a string — which is the part
 * that was unavailable before, and the reason three error contracts could coexist.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** The 404 case gets its own predicate; "not found" is a branch, not a message. */
  get isNotFound(): boolean {
    return this.status === 404;
  }
}

/**
 * Perform one request against one base and return the parsed body.
 *
 * `headers` is applied *after* the spread so a caller can override `Content-Type` (to send
 * nothing, or a form body) without the call itself silently becoming headerless.
 */
export async function request<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail = body.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail !== undefined
          ? JSON.stringify(detail)
          : res.statusText;
    throw new ApiError(res.status, detail, message);
  }
  return res.json() as Promise<T>;
}

/** Bind `request` to one base, so a client keeps a one-argument call signature. */
export function clientFor(base: string) {
  return <T>(path: string, init?: RequestInit): Promise<T> => request<T>(base, path, init);
}
