// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { SignalTable } from "./SignalTable";

let root: Root;
let container: HTMLDivElement;
beforeEach(async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  await i18n.changeLanguage("en");
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});
const cells = (index: number) =>
  [...container.querySelectorAll("tbody tr")[index].querySelectorAll("td")].map(
    (cell) => cell.textContent,
  );

it("combines mean and standard deviation with stable data bars and defaults to buyable only", async () => {
  await act(async () =>
    root.render(
      <SignalTable
        previous={[]}
        rows={[
          {
            rank: 1,
            ts_code: "A",
            pred: 2,
            pred_seed_0: 1,
            pred_seed_1: 3,
            pred_seed_2: null,
            pred_seed_3: Infinity,
            is_buyable_at_signal: true,
          },
          {
            rank: 2,
            ts_code: "B",
            pred: 4,
            pred_seed_0: 4,
            pred_seed_1: "bad",
            is_buyable_at_signal: false,
          },
          { rank: 3, ts_code: "C", pred: 5, is_buyable_at_signal: true },
        ]}
      />,
    ),
  );
  expect(container.querySelector("thead")?.textContent).not.toContain(
    "pred_seed_",
  );
  expect(
    container.querySelector<HTMLInputElement>('input[type="checkbox"]')
      ?.checked,
  ).toBe(true);
  expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
  expect(cells(1).slice(0, 5)).toEqual(["2", "1", "A", "—", "2.0000 ± 1.0000"]);
  expect(cells(0)[4]).toBe("5.0000 ± —");
  expect(
    container.querySelector<HTMLElement>(".summary-data-bar")?.style.width,
  ).toBe("100%");
  expect(container.querySelector(".online-report-toolbar")).toBeNull();
  await act(async () =>
    container
      .querySelector<HTMLInputElement>('input[type="checkbox"]')!
      .click(),
  );
  expect(container.querySelectorAll("tbody tr")).toHaveLength(3);
  expect(cells(2)[4]).toBe("4.0000 ± 0.0000");
  expect(
    container.querySelector<HTMLElement>(".summary-data-bar")?.style.width,
  ).toBe("100%");
  await act(async () =>
    container.querySelectorAll<HTMLButtonElement>("thead button")[4].click(),
  );
  expect(cells(0)[2]).toBe("A");
  await act(async () =>
    container.querySelectorAll<HTMLButtonElement>("thead button")[4].click(),
  );
  expect(cells(0)[2]).toBe("C");
});

it("retains the actual ranking score when a non-mean aggregation method is used", async () => {
  await act(async () =>
    root.render(
      <SignalTable
        previous={[]}
        scoreMethod="rank_mean"
        rows={[
          {
            rank: 1,
            ts_code: "A",
            pred: 0.75,
            pred_seed_0: 1,
            pred_seed_1: 3,
            is_buyable_at_signal: true,
          },
        ]}
      />,
    ),
  );
  expect(cells(0).slice(4, 6)).toEqual(["0.7500", "2.0000 ± 1.0000"]);
});

it("defaults to the recorded pool and recomputes pool ranks when inspecting another pool", async () => {
  await act(async () =>
    root.render(
      <SignalTable
        previous={[]}
        recordedUniverse={{
          kind: "percentile",
          field: "amount_to_signal",
          top_percent: 50,
        }}
        rows={[
          {
            rank: 1,
            ts_code: "A",
            pred: 0.9,
            amount_to_signal: 100,
            is_buyable_at_signal: true,
          },
          {
            rank: 2,
            ts_code: "B",
            pred: 0.8,
            amount_to_signal: 200,
            is_buyable_at_signal: true,
          },
          {
            rank: 3,
            ts_code: "C",
            pred: 0.7,
            amount_to_signal: 1000,
            is_buyable_at_signal: false,
          },
        ]}
      />,
    ),
  );
  const select = container.querySelector<HTMLSelectElement>(
    ".online-pool-picker select",
  )!;
  expect(select.value).toBe("amount_to_signal_top_50");
  expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
  expect(cells(0).slice(0, 3)).toEqual(["1", "2", "B"]);
  await act(async () => {
    select.value = "all";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
  expect(cells(0).slice(0, 3)).toEqual(["1", "1", "A"]);
  expect(container.textContent).toContain(
    i18n.t("onlineReport.viewPoolOnly", {
      pool: i18n.t("onlineReport.pools.amount_to_signal", { percent: 50 }),
    }),
  );
  expect(
    container.querySelector<HTMLOptionElement>('option[value="hs300"]')!
      .disabled,
  ).toBe(true);
});

it("explains missing context for the recorded pool rather than silently showing all stocks", async () => {
  await act(async () =>
    root.render(
      <SignalTable
        previous={[]}
        recordedUniverse={{ kind: "index", index_codes: ["hs300"] }}
        rows={[
          { rank: 1, ts_code: "A", pred: 0.9, is_buyable_at_signal: true },
        ]}
      />,
    ),
  );
  expect(container.querySelector('[role="status"]')?.textContent).toBe(
    i18n.t("onlineReport.missingPoolContext"),
  );
  expect(container.textContent).not.toContain("0.9000");
});

it.each(["en", "zh"])(
  "renders translated ranking headers in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    await act(async () =>
      root.render(
        <SignalTable
          rows={[
            { rank: 1, ts_code: "A", pred: 1, is_buyable_at_signal: true },
          ]}
          previous={[]}
        />,
      ),
    );
    const headers = container.querySelector("thead")!.textContent!;
    expect(headers).toContain(i18n.t("onlineReport.columns.pool_rank"));
    expect(headers).toContain(i18n.t("onlineReport.columns.original_rank"));
    expect(headers).not.toContain("onlineReport.");
  },
);
