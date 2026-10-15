import { RefreshCw, Search } from "lucide-react";

/** Shared task index heading, refresh and search used by research workbenches. */
export function RunIndexControls({
  title,
  count,
  loading,
  query,
  searchLabel,
  refreshLabel,
  onRefresh,
  onQuery,
}: {
  title: string;
  count: number;
  loading: boolean;
  query: string;
  searchLabel: string;
  refreshLabel: string;
  onRefresh: () => void;
  onQuery: (value: string) => void;
}) {
  return (
    <>
      <header className="run-index-header rail-header">
        <div className="run-index-heading rail-heading">
          <small>TASK VERSIONS</small>
          <strong>{title}</strong>
        </div>
        <div className="run-index-tools">
          <em>{count}</em>
          <button
            className="run-index-refresh rail-refresh"
            aria-label={refreshLabel}
            onClick={onRefresh}
          >
            <RefreshCw className={loading ? "spin" : ""} />
          </button>
        </div>
      </header>
      <label className="run-index-search rail-search">
        <Search />
        <input
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          placeholder={searchLabel}
          aria-label={searchLabel}
        />
      </label>
    </>
  );
}
