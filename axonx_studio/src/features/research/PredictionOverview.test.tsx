import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import i18n from "../../i18n";
import { taskStatus } from "../../playground/data";
import { PredictionOverview } from "./PredictionOverview";
import type { ResearchTask } from "./types";

// @vitest-environment jsdom

let root: Root;
let container: HTMLDivElement;
const meta: ResearchTask<"predict"> = {
  ...taskStatus("predict", "predict#demo"),
  task_type: "predict",
  created_at: "",
  reg_name: "predict",
  output_params: {
    rows: 4,
    date_range: {},
    output_columns: ["signal_price", "is_buyable_at_signal"],
    protocol: {},
    statistics: {},
    artifacts: {},
  },
};
beforeEach(() => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  delete document.documentElement.dataset.theme;
});

describe("prediction overview", () => {
  it.each(["en", "zh"])(
    "renders missing statistics and current columns in %s",
    async (language) => {
      await i18n.changeLanguage(language);
      await act(async () =>
        root.render(
          <PredictionOverview
            meta={{
              ...meta,
              output_params: { ...meta.output_params, statistics: {} },
            }}
          />,
        ),
      );
      expect(container.textContent).toContain("—");
      expect(container.textContent).toContain("signal_price");
      expect(container.textContent).toContain(
        i18n.t("research.columns.is_buyable_at_signal"),
      );
      expect(container.textContent).not.toContain("actual_return");
      expect(container.textContent).not.toContain("valid_return_rows");
    },
  );

  it.each(["dark", "light"])(
    "renders signal-only coverage in %s theme at narrow width",
    async (theme) => {
      document.documentElement.dataset.theme = theme;
      container.style.width = "375px";
      await i18n.changeLanguage("en");
      await act(async () =>
        root.render(
          <PredictionOverview
            meta={{
              ...meta,
              output_params: {
                ...meta.output_params,
                statistics: {
                  pred: { mean: 0.25 },
                  days: 2,
                  symbols: 2,
                  buyable_rows: 2,
                  candidate_rows: 1,
                },
              },
            }}
          />,
        ),
      );
      expect(container.textContent).toContain("0.25");
      expect(container.textContent).toContain("50%");
      expect(container.textContent).toContain("25%");
      expect(container.textContent).not.toContain("valid_return_rows");
    },
  );
});
