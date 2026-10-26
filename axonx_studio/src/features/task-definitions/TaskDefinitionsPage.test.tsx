// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { definitions } from "../../playground/fixtures";
import { listTaskDefs } from "../tasks/api";
import TaskDefinitionsPage from "./TaskDefinitionsPage";

vi.mock("../tasks/api", () => ({ listTaskDefs: vi.fn() }));
afterEach(() => {
  vi.resetAllMocks();
  vi.unstubAllGlobals();
});

it.each(["en", "zh"])("shows read-only definitions in %s", async (language) => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  await i18n.changeLanguage(language);
  vi.mocked(listTaskDefs).mockResolvedValue(definitions);
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <TaskDefinitionsPage
          initialName={definitions[0].name}
          onConnection={vi.fn()}
        />,
      ),
    );
    expect(container.querySelectorAll("pre")).toHaveLength(2);
    expect(
      container.querySelector("form, .submit-button, .form-footer"),
    ).toBeNull();
    expect(container.textContent).toContain(definitions[0].name);
    expect(JSON.parse(container.querySelector("pre")!.textContent!)).toEqual(
      definitions[0].input_schema,
    );
  } finally {
    await act(async () => root.unmount());
  }
});

it("aborts an obsolete machine request and ignores its late result", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  let finish!: (value: typeof definitions) => void;
  vi.mocked(listTaskDefs)
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    )
    .mockResolvedValueOnce([]);
  const onConnection = vi.fn();
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <TaskDefinitionsPage target="first" onConnection={onConnection} />,
      ),
    );
    const signal = vi.mocked(listTaskDefs).mock.calls[0][1];
    await act(async () =>
      root.render(
        <TaskDefinitionsPage target="second" onConnection={onConnection} />,
      ),
    );
    expect(signal?.aborted).toBe(true);
    await act(async () => finish(definitions));
    expect(container.querySelectorAll(".catalog-task")).toHaveLength(0);
    expect(onConnection).toHaveBeenCalledTimes(1);
  } finally {
    await act(async () => root.unmount());
  }
});
