// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "../../i18n";
import { definitions } from "../../playground/data";
import { executeTaskCommand, getTaskStatus, listTaskDefs } from "./api";
import { TaskExecutionOutput, TaskRunForm } from "./TaskExecution";
import { TaskExecutionStore } from "./execution";
import TaskDefinitionsPage from "./TaskDefinitionsPage";

vi.mock("./api", () => ({
  listTaskDefs: vi.fn(),
  executeTaskCommand: vi.fn(),
  getTaskStatus: vi.fn(),
}));
afterEach(() => {
  vi.resetAllMocks();
  vi.unstubAllGlobals();
});

it("renders terminal exception logs without ANSI color sequences", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  const container = document.createElement("div");
  const root = createRoot(container);
  try {
    await act(async () =>
      root.render(
        <TaskExecutionOutput
          run={{
            id: "test",
            taskId: "base#demo#test",
            definition: "demo",
            machineId: "local",
            state: "failed",
            task: null,
            log: "\u001b[31mRuntimeError: failure\u001b[0m",
            error: "\u001b[1mfailure\u001b[0m",
            exitCode: 1,
            stopping: false,
          }}
        />,
      ),
    );
    expect(container.textContent).toContain("RuntimeError: failure");
    expect(container.textContent).not.toContain(String.fromCharCode(27));
  } finally {
    await act(async () => root.unmount());
  }
});

it("starts from schema defaults and keeps its command alive after unmount", async () => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  const store = new TaskExecutionStore();
  const container = document.createElement("div");
  const root = createRoot(container);
  vi.mocked(getTaskStatus).mockRejectedValue(new Error("Not created yet"));
  let finish!: (result: import("./api").CommandResult) => void;
  vi.mocked(executeTaskCommand).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await act(async () =>
    root.render(
      <TaskRunForm
        store={store}
        definition={{
          ...definitions[0],
          input_schema: {
            properties: {
              x: { type: "integer", default: 2 },
              y: { type: "integer", default: 3 },
            },
          },
        }}
        machineId="remote"
        target="remote:1024"
      />,
    ),
  );
  try {
    await act(async () =>
      container
        .querySelector("form")!
        .dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        ),
    );
    const [argv, options] = vi.mocked(executeTaskCommand).mock.calls[0];
    expect(argv).toContain("--x");
    expect(argv[argv.indexOf("--x") + 1]).toBe("2");
    expect(options?.target).toBe("remote:1024");
    expect(
      container.querySelector<HTMLButtonElement>('button[type="submit"]')!
        .disabled,
    ).toBe(true);
    await act(async () => root.unmount());
    expect(options?.signal?.aborted).toBe(false);
  } finally {
    finish({
      stdout: "{}",
      stderr: "",
      exit_code: 0,
      stdout_truncated: false,
      stderr_truncated: false,
    });
    store.dispose();
  }
});

it.each(["en", "zh"])(
  "shows editable inputs and readable output fields in %s",
  async (language) => {
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
      expect(container.querySelectorAll("pre")).toHaveLength(0);
      expect(container.querySelector("form")).not.toBeNull();
      expect(container.querySelector('button[type="submit"]')).not.toBeNull();
      expect(container.querySelector("details")).toBeNull();
      expect(container.textContent).toContain(definitions[0].name);
      expect(
        container.querySelector(".schema-output-fields")!.textContent,
      ).toContain("output_dir");
    } finally {
      await act(async () => root.unmount());
    }
  },
);

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
    const signal = vi.mocked(listTaskDefs).mock.calls[0][0]?.signal;
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
