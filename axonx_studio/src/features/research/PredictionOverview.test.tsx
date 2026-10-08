// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import i18n from "../../i18n";
import { PredictionOverview } from "./PredictionOverview";
import type { ResearchArtifact } from "./types";

let root: Root;
let container: HTMLDivElement;
const meta: ResearchArtifact = {
  _path: "predict/demo",
  task_key: "predict",
  created_at: "",
  rows: 4,
  config: { task_id: "predict#demo", task_type: "predict", task_name: "demo" },
  artifacts: {},
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
          <PredictionOverview meta={{ ...meta, prediction_statistics: {} }} />,
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
              prediction_statistics: {
                pred: { mean: 0.25 },
                days: 2,
                symbols: 2,
                buyable_rows: 2,
                candidate_rows: 1,
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
