// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { PortfolioSelector } from "./PortfolioSelector";

const identities: Record<string, unknown>[] = [
  {
    universe: { kind: "all" },
    strategy: { kind: "fixed_expiry", holding_days: 1 },
    top_n: 5,
  },
  {
    universe: { kind: "all" },
    strategy: { holding_days: 1, kind: "fixed_expiry" },
    top_n: 10,
  },
  {
    universe: { kind: "index", index_codes: ["hs300"] },
    strategy: { kind: "fixed_expiry", holding_days: 1 },
    top_n: 10,
  },
  {
    universe: { kind: "index", index_codes: ["hs300"] },
    strategy: { kind: "fixed_expiry", holding_days: 1 },
    top_n: 20,
  },
  {
    universe: { kind: "index", index_codes: ["hs300"] },
    strategy: { kind: "rank_retention", minimum_holding_days: 3 },
    top_n: 20,
    rebalance: null,
  },
  {
    universe: { kind: "index", index_codes: ["hs300"] },
    strategy: { kind: "rank_retention", minimum_holding_days: 3 },
    top_n: 20,
    rebalance: 0,
  },
];

function Selection() {
  const [selected, setSelected] = useState("0");
  return (
    <>
      <PortfolioSelector
        portfolios={identities.map((portfolio_id) => ({ portfolio_id }))}
        value={selected}
        onChange={setSelected}
      />
      <output>{selected}</output>
    </>
  );
}

it.each(["en", "zh"])(
  "cascades sparse identity dimensions and preserves compatible values in %s",
  async (language) => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    await i18n.changeLanguage(language);
    const container = document.createElement("div");
    const root = createRoot(container);
    const field = (key: string) =>
      container.querySelector<HTMLSelectElement>(
        `select[aria-label="${i18n.t("backtest.portfolio")} · ${key}"]`,
      )!;
    const choose = async (key: string, text: string) => {
      const select = field(key);
      const option = [...select.options].find((option) =>
        option.textContent!.includes(text),
      )!;
      await act(async () => {
        select.value = option.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });
    };
    try {
      await act(async () => root.render(<Selection />));
      expect(container.querySelectorAll("select")).toHaveLength(4);
      expect(field("strategy").options).toHaveLength(1);
      expect(field("strategy").disabled).toBe(true);
      expect(field("strategy").textContent).toContain("holding_days: 1");
      expect(field("rebalance").textContent).toContain(
        i18n.t("portfolio.unspecified"),
      );

      await choose("top_n", "10");
      expect(container.querySelector("output")!.textContent).toBe("1");
      await choose("universe", "hs300");
      expect(container.querySelector("output")!.textContent).toBe("2");
      expect(field("top_n").value).toBe("10");
      expect(
        [...field("top_n").options].map((option) => option.textContent),
      ).toEqual(["10", "20"]);

      await choose("strategy", "rank_retention");
      expect(container.querySelector("output")!.textContent).toBe("4");
      expect(field("top_n").value).toBe("20");
      expect(field("top_n").disabled).toBe(true);
      expect(field("rebalance").value).toBe("null");
      expect(
        [...field("rebalance").options].map((option) => option.textContent),
      ).toEqual(["null", "0"]);
      await choose("rebalance", "0");
      expect(container.querySelector("output")!.textContent).toBe("5");
      await choose("universe", "all");
      expect(["0", "1"]).toContain(
        container.querySelector("output")!.textContent,
      );
      expect(field("rebalance").value).toBe("undefined");
    } finally {
      await act(async () => root.unmount());
    }
  },
);
