import { useTranslation } from "react-i18next";
import { Select } from "../../shared/ui/Select";
import { portfolioFields, portfolioValueLabel } from "./portfolio";

export function PortfolioSelector({
  portfolios,
  value,
  onChange,
  label,
}: {
  portfolios: { portfolio_id: Record<string, unknown> }[];
  value: string;
  onChange: (value: string) => void;
  label?: string;
}) {
  const { t } = useTranslation();
  const title = label || t("backtest.portfolio");
  const fields = portfolioFields(
    portfolios.map((item) => item.portfolio_id),
    Number(value),
  );
  return (
    <fieldset className="portfolio-selector">
      <legend>{title}</legend>
      <div className="portfolio-fields">
        {fields.map((field) => (
          <label key={field.key}>
            <span>{field.key}</span>
            <Select
              aria-label={`${title} · ${field.key}`}
              value={field.value}
              disabled={field.options.size === 1}
              onChange={(event) =>
                onChange(String(field.options.get(event.target.value)!.index))
              }
            >
              {[...field.options].map(([token, option]) => (
                <option key={token} value={token}>
                  {option.value === undefined
                    ? t("portfolio.unspecified")
                    : portfolioValueLabel(option.value)}
                </option>
              ))}
            </Select>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
