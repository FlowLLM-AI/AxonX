import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ArtifactRecord } from "../../shared/api/contracts";
import { isArtifactRecord } from "../../shared/api/artifacts";
import { taskDirectory } from "../../shared/lib/tasks";
import { useAsyncResource } from "../../shared/hooks/useAsyncResource";
import { getTaskStatus } from "../tasks/api";
import { previewWorkspaceFile } from "../workspace/api";
import { ModelPicker } from "./ModelPicker";
import { ReportTable } from "./ReportTable";
import {
  parseTopComparison,
  topRows,
  TOP_NS,
  type TopStock,
} from "./topComparisonData";

export function TopComparison({
  taskId,
  startedAt,
  artifact,
  target,
  windowKey,
  status,
  reason,
}: {
  taskId: string;
  startedAt: string;
  artifact?: ArtifactRecord;
  target?: string;
  windowKey: string;
  status?: string;
  reason?: string;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState("");
  const [n, setN] = useState<number>(10);
  const [scope, setScope] = useState<"buyable" | "all">("buyable");
  const [onlyDifferences, setOnlyDifferences] = useState(false);
  const load = useCallback(
    async (signal: AbortSignal) => {
      if (!artifact || !taskId || !startedAt) return null;
      if (!isArtifactRecord(artifact))
        throw new Error(t("topComparison.invalid"));
      const verifyTask = async () => {
        const owner = await getTaskStatus(taskId, target, signal);
        signal.throwIfAborted();
        if (owner.started_at !== startedAt)
          throw new Error(t("onlinePipeline.replacedChild"));
      };
      await verifyTask();
      const preview = await previewWorkspaceFile(
        `${taskDirectory(taskId)}/${artifact.path}`,
        0,
        1,
        target,
        signal,
      );
      await verifyTask();
      if (preview.kind !== "json" || preview.parse_error || preview.truncated)
        throw new Error(t("topComparison.invalid"));
      const data = parseTopComparison(preview.data);
      if (data.key !== windowKey) throw new Error(t("topComparison.invalid"));
      return data;
    },
    [artifact, taskId, startedAt, target, windowKey, t],
  );
  const { data, error, loading, reload } = useAsyncResource(load);
  if (!artifact)
    return <p className="compare-empty">{t("topComparison.unavailable")}</p>;
  if (error)
    return (
      <p role="alert">
        {error} <button onClick={() => void reload()}>{t("retry")}</button>
      </p>
    );
  if (!data)
    return (
      <p>{loading ? t("shell.loading") : t("topComparison.unavailable")}</p>
    );
  const rows = topRows(data, scope, n);
  const pair = (a?: number, b?: number, precision = 6) =>
    `${a === undefined ? "—" : a.toFixed(precision)} / ${b === undefined ? "—" : b.toFixed(precision)}`;
  const sides = (r: Record<string, unknown>) =>
    [
      r.online as TopStock | undefined,
      r.offline as TopStock | undefined,
    ] as const;
  const filters = (
    <div className="top-comparison-filters">
      <div className="comparison-top-picker">
        <ModelPicker
          label={t("topComparison.topN")}
          models={TOP_NS.map(String)}
          labels={Object.fromEntries(
            TOP_NS.map((size) => [String(size), `Top ${size}`]),
          )}
          value={String(n)}
          onChange={(value) => {
            setN(Number(value));
            setExpanded("");
          }}
        />
      </div>
      <div className="comparison-pool-picker">
        <ModelPicker
          label={t("topComparison.scope")}
          models={["buyable", "all"]}
          labels={{
            buyable: t("topComparison.buyable"),
            all: t("topComparison.all"),
          }}
          value={scope}
          onChange={(value) => {
            setScope(value as "buyable" | "all");
            setExpanded("");
          }}
        />
      </div>
      <label className="compare-difference-filter">
        <input
          type="checkbox"
          checked={onlyDifferences}
          onChange={(e) => setOnlyDifferences(e.target.checked)}
        />
        {t("topComparison.onlyDifferences")}
      </label>
    </div>
  );
  const selection =
    data.score_selection.seed === null
      ? data.score_selection.aggregation
      : `seed_${data.score_selection.seed}`;
  return (
    <section className="top-comparison">
      <div
        className="top-comparison-summary"
        title={`${t("topComparison.order")} · ${t("topComparison.stdHint")} · ${t("topComparison.selection")} ${selection}`}
      >
        {status && (
          <span className={`online-status status-${status}`}>
            {t(`onlinePipeline.status.${status}`, status)}
          </span>
        )}
        <span>{data.key}</span>
        <span>
          {t("topComparison.counts", {
            online: data.scopes[scope].online.count.toLocaleString(),
            offline: data.scopes[scope].offline.count.toLocaleString(),
          })}
        </span>
        <span className="top-overlap">
          {t("topComparison.overlap", {
            count: rows.filter((r) => r.membership === "both").length,
            n,
          })}
        </span>
        {data.mock_online && (
          <span className="online-status status-incomplete">
            {t("topComparison.mock")}
          </span>
        )}
        {reason && <span>{t(`onlinePipeline.reasons.${reason}`, reason)}</span>}
        <span
          className="top-comparison-info"
          aria-label={`${t("topComparison.order")} · ${t("topComparison.stdHint")}`}
        >
          ⓘ
        </span>
      </div>
      <ReportTable
        key={`${scope}:${n}:${onlyDifferences}`}
        actions={filters}
        rows={onlyDifferences ? rows.filter((r) => r.different) : rows}
        columns={[
          {
            key: "code",
            label: t("topComparison.code"),
            render: (r) => (
              <code className="compare-stock-code">{String(r.code)}</code>
            ),
          },
          {
            key: "name",
            label: t("topComparison.name"),
            render: (r) => (
              <button
                className="compare-stock-button"
                aria-expanded={expanded === r.code}
                onClick={() =>
                  setExpanded(expanded === r.code ? "" : String(r.code))
                }
                title={`${(r.online as TopStock | undefined)?.name || "—"} / ${(r.offline as TopStock | undefined)?.name || "—"}`}
              >
                {String(r.name)}
              </button>
            ),
          },
          {
            key: "membership",
            label: t("topComparison.membership"),
            render: (r) => (
              <span
                className={`online-status status-${r.membership === "both" ? "consistent" : "different"}`}
              >
                {t(`topComparison.${r.membership}`)}
              </span>
            ),
          },
          {
            key: "rank",
            label: t("topComparison.rank"),
            render: (r) => {
              const [a, b] = sides(r);
              return pair(a?.rank ?? undefined, b?.rank ?? undefined, 0);
            },
          },
          {
            key: "score",
            label: t("topComparison.score"),
            render: (r) => {
              const [a, b] = sides(r);
              return pair(a?.score, b?.score);
            },
          },
          {
            key: "delta",
            label: t("topComparison.delta"),
            render: (r) =>
              typeof r.delta === "number" ? r.delta.toExponential(3) : "—",
          },
          {
            key: "std",
            label: t("topComparison.std"),
            render: (r) => {
              const [a, b] = sides(r);
              return pair(a?.std, b?.std);
            },
          },
        ]}
        renderExpanded={(r) => {
          if (expanded !== r.code) return null;
          const [a, b] = sides(r);
          return (
            <div className="top-seeds">
              <p>
                {t("topComparison.names")}: {a?.name || "—"} / {b?.name || "—"}
              </p>
              <table>
                <thead>
                  <tr>
                    <th>Seed</th>
                    <th>{t("topComparison.score")}</th>
                    <th>{t("topComparison.delta")}</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ...new Set([
                      ...Object.keys(a?.seeds || {}),
                      ...Object.keys(b?.seeds || {}),
                    ]),
                  ].map((seed) => (
                    <tr key={seed}>
                      <td>{seed}</td>
                      <td>{pair(a?.seeds[seed], b?.seeds[seed])}</td>
                      <td>
                        {a?.seeds[seed] !== undefined &&
                        b?.seeds[seed] !== undefined
                          ? (a.seeds[seed] - b.seeds[seed]).toExponential(3)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }}
      />
    </section>
  );
}
