import { useCallback, useState } from "react";

import { api, SearchResult } from "../lib/api";
import { SearchPage } from "../pages/SearchPage";

/**
 * Container: wires SearchPage to the real /api/v1/search endpoint.
 * The page manages its own query/results UI state; this container only
 * provides the onSearch handler that talks to the backend.
 */
export function SearchContainer() {
  const [backendError, setBackendError] = useState<string | null>(null);

  const handleSearch = useCallback(
    async (query: string, sourceFilter: string): Promise<SearchResult[]> => {
      try {
        setBackendError(null);
        const response = await api.search(query, {
          source_ids: sourceFilter || undefined,
        });
        return response.results;
      } catch (err) {
        setBackendError(err instanceof Error ? err.message : String(err));
        return [];
      }
    },
    [],
  );

  return (
    <>
      {backendError && (
        <p data-testid="search-error" style={{ color: "var(--c-danger)" }}>
          Search failed: {backendError}
        </p>
      )}
      <SearchPage onSearch={handleSearch} />
    </>
  );
}
