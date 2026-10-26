import { RefreshCw, Search } from "lucide-react";

/** Shared task index heading, refresh and search used by research workbenches. */
export function TaskIndexControls({
  title,
  eyebrow = "TASKS",
  count,
  loading,
  query,
  searchLabel,
  refreshLabel,
  onRefresh,
  onQuery,
}: {
  title: string;
  eyebrow?: string;
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
      <header className="task-index-header rail-header">
        <div className="task-index-heading rail-heading">
          <small>{eyebrow}</small>
          <strong>{title}</strong>
        </div>
        <div className="task-index-tools">
          <em>{count}</em>
          <button
            className="task-index-refresh rail-refresh"
            aria-label={refreshLabel}
            onClick={onRefresh}
          >
            <RefreshCw className={loading ? "spin" : ""} />
          </button>
        </div>
      </header>
      <label className="task-index-search rail-search">
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
