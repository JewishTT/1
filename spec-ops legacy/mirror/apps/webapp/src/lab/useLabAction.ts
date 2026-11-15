import { useCallback, useState } from "react";

import { ApiError } from "../lib/http";

export function labErrorText(err: unknown): string {
  if (err instanceof ApiError) {
    const detail = err.detail;
    if (detail && typeof detail === "object") {
      const value = detail as { error?: unknown; reason?: unknown; rejected?: unknown };
      const parts = [value.error, value.reason].filter(
        (part): part is string => typeof part === "string" && part.length > 0,
      );
      if (parts.length > 0) return `${err.status} ${parts.join(": ")}`;
    }
    return `${err.status} ${err.message}`;
  }
  return err instanceof Error ? err.message : String(err);
}

export function useLabAction(refresh: () => Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const run = useCallback(
    async (action: () => Promise<unknown>, success: string) => {
      setBusy(true);
      setNote(null);
      try {
        await action();
        await refresh();
        setNote(success);
      } catch (err) {
        setNote(labErrorText(err));
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  return { busy, note, setNote, run };
}
