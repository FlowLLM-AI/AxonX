// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { seed } from "../../playground/fixtures";
import { TaskIssues } from "./TaskIssues";
import type { TaskNode } from "./tree";

let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});
const issue = (name: string): TaskNode => ({
  record: {
    ...seed().tasks.get("base#playground_online#demo")!.children[0],
    node_name: name,
  },
  status: null,
  error: "Old child Task unavailable",
  issue: "replaced",
});
it.each(["en", "zh"])(
  "consolidates unavailable child Tasks without suggesting another refresh in %s",
  async (language) => {
    await i18n.changeLanguage(language);
    const nodes = [issue("history-1445"), issue("v1-1445"), issue("v2-1445")];
    await act(async () => root.render(<TaskIssues nodes={nodes} />));
    expect(container.querySelectorAll('[role="status"]')).toHaveLength(1);
    expect(container.querySelectorAll('[role="alert"]')).toHaveLength(0);
    expect(container.querySelector("p")?.textContent).toBe(
      i18n.t("onlinePipeline.replacedChildren", { count: 3 }),
    );
    expect(container.textContent).not.toContain(
      i18n.t("onlinePipeline.restartedTask"),
    );
    expect(container.querySelector("small")?.textContent).toContain("v2-1445");
    // Refreshing the same historical references must not multiply notices.
    await act(async () =>
      root.render(<TaskIssues nodes={structuredClone(nodes)} />),
    );
    expect(container.querySelectorAll(".task-execution-notice")).toHaveLength(
      1,
    );
  },
);
it("retains unrelated request failures and clears notices when metadata becomes available", async () => {
  await i18n.changeLanguage("en");
  const failure = {
    ...issue("unreachable"),
    issue: undefined,
    error: "Service unavailable",
  };
  await act(async () =>
    root.render(
      <TaskIssues nodes={[issue("history"), failure, { ...failure }]} />,
    ),
  );
  expect(container.querySelectorAll('[role="alert"]')).toHaveLength(1);
  expect(container.querySelector('[role="alert"]')?.textContent).toContain(
    "Service unavailable",
  );
  await act(async () => root.render(<TaskIssues nodes={[]} />));
  expect(container.textContent).toBe("");
});
