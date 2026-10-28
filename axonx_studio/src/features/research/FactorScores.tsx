import { useState } from "react";
import { useTranslation } from "react-i18next";
import { formatNumber as fmt } from "../../shared/lib/format";
import { Select } from "../../shared/ui/Select";

export function AnalysisScores({
  scores,
}: {
  scores: Record<string, Record<string, number>>;
}) {
  const { t } = useTranslation();
  const [chosenMetric, setChosenMetric] = useState("");
  const [chosenLabel, setChosenLabel] = useState("");
  const groups = Object.entries(scores).map(([key, values]) => {
    const separator = key.indexOf("/");
    return {
      metric: separator < 0 ? key : key.slice(0, separator),
      label: separator < 0 ? "—" : key.slice(separator + 1),
      values,
    };
  });
  if (!groups.length) return null;
  const metrics = [...new Set(groups.map((group) => group.metric))];
  const metric = metrics.includes(chosenMetric) ? chosenMetric : metrics[0];
  const labels = [
    ...new Set(
      groups
        .filter((group) => group.metric === metric)
        .map((group) => group.label),
    ),
  ];
  const label = labels.includes(chosenLabel) ? chosenLabel : labels[0];
  const values =
    groups.find((group) => group.metric === metric && group.label === label)
      ?.values || {};
  const rows = Object.entries(values).sort(
    ([nameA, valueA], [nameB, valueB]) =>
      Math.abs(valueB) - Math.abs(valueA) || nameA.localeCompare(nameB),
  );
  const maxAbs = Math.max(...rows.map(([, value]) => Math.abs(value)), 0);

  return (
    <section className="viz-card wide analysis-score-card">
      <header>
        <div>
          <small>SCORES</small>
          <h3>{t("research.factor_scores")}</h3>
        </div>
        <div className="analysis-score-controls">
          <label>
            <span>{t("research.metric")}</span>
            <Select
              value={metric}
              onChange={(event) => setChosenMetric(event.target.value)}
            >
              {metrics.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </label>
          <label>
            <span>{t("research.label")}</span>
            <Select
              value={label}
              onChange={(event) => setChosenLabel(event.target.value)}
            >
              {labels.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </label>
          <span className="analysis-score-count">{rows.length}</span>
        </div>
      </header>
      <div className="analysis-score-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("research.factor")}</th>
              <th>{t("research.magnitude")}</th>
              <th>{t("research.score")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([factor, value]) => {
              const width = maxAbs ? (Math.abs(value) / maxAbs) * 50 : 0;
              return (
                <tr key={factor}>
                  <td>
                    <code>{factor}</code>
                  </td>
                  <td>
                    <div className="analysis-score-bar" aria-hidden="true">
                      <span
                        className={value < 0 ? "negative" : "positive"}
                        style={{
                          left: `${value < 0 ? 50 - width : 50}%`,
                          width: `${width}%`,
                        }}
                      />
                    </div>
                  </td>
                  <td>{fmt(value, 4)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
