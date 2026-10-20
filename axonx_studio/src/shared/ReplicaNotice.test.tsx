// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it } from "vitest";
import i18n from "../i18n";
import { ReplicaNotice } from "./ReplicaNotice";
import type { DisplayReplica } from "./lib/replica";

const replica: DisplayReplica = {
  purpose: "display",
  snapshot: null,
  log: null,
  source_revision: "a".repeat(64),
  policy_revision: "b".repeat(64),
  files: {
    "dataset.parquet": {
      size: 100,
      revision: "file-v1",
      sampled: true,
      rows: 100,
      source_rows: 500,
      dates: ["20260105", "20260106"],
    },
  },
  omitted: { "inputs/": "upstream input snapshot" },
  source_log_path: "/source/logs/run.log",
};
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  dispose = undefined;
});
it.each(["en", "zh"])(
  "shows sampled coverage and omitted inputs in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    dispose = () => {
      act(() => root.unmount());
      container.remove();
    };
    await act(async () => {
      root.render(<ReplicaNotice replica={replica} />);
    });
    expect(container.querySelector("details")?.open).toBe(false);
    expect(container.textContent).toContain(i18n.t("replica.coverage"));
    expect(container.textContent).toContain(i18n.t("replica.label"));
    expect(container.textContent).toContain("20260105");
    expect(container.textContent).toContain("20260106");
    expect(container.textContent).toContain("100");
    expect(container.textContent).toContain("500");
    expect(container.textContent).toContain("inputs/");
  },
);
