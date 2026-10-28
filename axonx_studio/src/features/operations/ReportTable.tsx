import { Fragment, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { ValueFormat } from "../../shared/lib/format";
import { formatTableValue as display } from "../../shared/lib/format";

export interface Column {
  key: string;
  label: string;
  render?: (row: Record<string, unknown>) => ReactNode;
  format?: ValueFormat;
}

export function ReportTable({
  rows,
  columns,
  defaultSort,
  actions,
  renderExpanded,
}: {
  rows: Record<string, unknown>[];
  columns: Column[];
  defaultSort?: string;
  actions?: ReactNode;
  renderExpanded?: (row: Record<string, unknown>) => ReactNode;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState({
    key: defaultSort || "",
    descending: false,
  });
  const [page, setPage] = useState(0);
  const selected = useMemo(() => {
    const filtered = rows.filter((row) =>
      columns.some(({ key }) =>
        String(row[key] ?? "")
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    );
    if (sort.key)
      filtered.sort((a, b) => {
        const left = a[sort.key],
          right = b[sort.key];
        if (left == null) return right == null ? 0 : 1;
        if (right == null) return -1;
        const delta =
          typeof left === "number" && typeof right === "number"
            ? left - right
            : String(left).localeCompare(String(right));
        return sort.descending ? -delta : delta;
      });
    return filtered;
  }, [rows, columns, query, sort]);
  const pages = Math.max(1, Math.ceil(selected.length / 50));
  const current = Math.min(page, pages - 1);
  return (
    <section className="online-table-card">
      <div className="online-table-tools">
        <input
          aria-label={t("onlineReport.search")}
          placeholder={t("onlineReport.search")}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
        />
        <div className="online-table-actions">
          <span>
            {selected.length.toLocaleString()} {t("onlinePipeline.rows")}
          </span>
          {actions}
        </div>
      </div>
      {!selected.length ? (
        <div className="empty-state">{t("onlineReport.noRows")}</div>
      ) : (
        <div className="online-table-scroll">
          <table>
            <thead>
              <tr>
                {columns.map(({ key, label }) => (
                  <th
                    key={key}
                    aria-sort={
                      sort.key === key
                        ? sort.descending
                          ? "descending"
                          : "ascending"
                        : "none"
                    }
                  >
                    <button
                      onClick={() =>
                        setSort({
                          key,
                          descending: sort.key === key && !sort.descending,
                        })
                      }
                    >
                      {label}
                      {sort.key === key ? (sort.descending ? " ↓" : " ↑") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {selected
                .slice(current * 50, (current + 1) * 50)
                .map((row, index) => {
                  const expanded = renderExpanded?.(row);
                  return (
                    <Fragment key={index}>
                      <tr>
                        {columns.map(({ key, format, render }) => (
                          <td
                            key={key}
                            className={
                              key === "rank_change" && Number(row[key]) > 0
                                ? "online-positive"
                                : ""
                            }
                          >
                            {render ? (
                              render(row)
                            ) : format === "boolean" &&
                              typeof row[key] === "boolean" ? (
                              <span
                                className={`online-status status-${row[key] ? "done" : "incomplete"}`}
                              >
                                {t(
                                  row[key]
                                    ? "onlineReport.buyable"
                                    : "onlineReport.blocked",
                                )}
                              </span>
                            ) : typeof row[key] === "boolean" ? (
                              t(
                                row[key]
                                  ? "onlineReport.yes"
                                  : "onlineReport.no",
                              )
                            ) : [
                                "side",
                                "status",
                                "reason",
                                "period_type",
                                "period",
                              ].includes(key) &&
                              typeof row[key] === "string" ? (
                              t(
                                `onlineReport.values.${String(row[key])}`,
                                display(row[key], format),
                              )
                            ) : (
                              display(row[key], format)
                            )}
                          </td>
                        ))}
                      </tr>
                      {expanded && (
                        <tr className="online-expanded-row">
                          <td colSpan={columns.length}>{expanded}</td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
            </tbody>
          </table>
        </div>
      )}
      {pages > 1 && (
        <div className="online-table-tools">
          <button
            className="secondary-button"
            disabled={!current}
            onClick={() => setPage(current - 1)}
          >
            {t("onlineReport.previous")}
          </button>
          <span>
            {current + 1} / {pages}
          </span>
          <button
            className="secondary-button"
            disabled={current === pages - 1}
            onClick={() => setPage(current + 1)}
          >
            {t("onlineReport.next")}
          </button>
        </div>
      )}
    </section>
  );
}
