// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import WorkspaceBrowserPage from "./WorkspaceBrowserPage";
import { listWorkspaceEntries, previewWorkspaceFile } from "./api";
import type {
  WorkspaceDirectory,
  WorkspaceEntry,
  WorkspacePreview,
} from "./types";

vi.mock("./api", () => ({
  listWorkspaceEntries: vi.fn(),
  previewWorkspaceFile: vi.fn(),
}));
vi.mock("react-i18next", async (importOriginal) => {
  const t = (key: string) => key;
  return {
    ...(await importOriginal<typeof import("react-i18next")>()),
    useTranslation: () => ({ t }),
  };
});
vi.mock("./FilePreview", () => ({
  FilePreview: ({ preview }: { preview: WorkspacePreview }) => (
    <div data-preview>{JSON.stringify(preview)}</div>
  ),
}));

const onConnection = vi.fn();
let root: Root;
let container: HTMLDivElement;
function entry(
  path: string,
  kind: WorkspaceEntry["kind"] = "directory",
): WorkspaceEntry {
  return {
    name: path.split("/").at(-1)!,
    path,
    kind,
    preview_kind: kind === "file" ? "text" : null,
    supported: kind === "file",
    size: null,
    modified_at: 0,
  };
}
function directory(
  path: string,
  entries: WorkspaceEntry[] = [],
  truncated = false,
): WorkspaceDirectory {
  return { path, entries, truncated };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}
function Browser({ target, path }: { target: string; path?: string }) {
  const [selectedPath, setPath] = useState(path);
  return (
    <WorkspaceBrowserPage
      target={target}
      initialPath={selectedPath}
      onPathChange={setPath}
      onConnection={onConnection}
    />
  );
}
async function render(path?: string, target = "machine-a") {
  await act(async () => {
    root.render(
      <Browser key={`${target}:${path || ""}`} target={target} path={path} />,
    );
  });
}
async function click(selector: string) {
  const button = container.querySelector<HTMLButtonElement>(selector);
  expect(button).not.toBeNull();
  await act(async () => button!.click());
}
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  vi.resetAllMocks();
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  vi.mocked(listWorkspaceEntries).mockResolvedValue(directory(""));
  vi.mocked(previewWorkspaceFile).mockResolvedValue({
    kind: "text",
    content: "hello",
    size: 5,
    truncated: false,
  });
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe("workspace browser", () => {
  it("opens the entire workspace and preserves service directory ordering", async () => {
    vi.mocked(listWorkspaceEntries).mockResolvedValue(
      directory("", [
        entry("2025"),
        entry("2026"),
        entry("agents"),
        entry("tushare"),
      ]),
    );
    await render();
    expect(listWorkspaceEntries).toHaveBeenCalledWith(
      "",
      "machine-a",
      expect.any(AbortSignal),
      0,
    );
    expect(
      [...container.querySelectorAll("nav button[title]")].map((button) =>
        button.getAttribute("title"),
      ),
    ).toEqual(["2025", "2026", "agents", "tushare"]);
    expect(previewWorkspaceFile).not.toHaveBeenCalled();
  });

  it("reveals arbitrary nested files beyond the first directory page", async () => {
    vi.mocked(listWorkspaceEntries).mockImplementation(
      async (path, _target, _signal, offset) => {
        if (path === "")
          return offset
            ? directory("", [entry("models")])
            : directory("", [entry("agents")], true);
        return directory("models", [entry("models/report.txt", "file")]);
      },
    );
    await render("models/report.txt");
    expect(listWorkspaceEntries).toHaveBeenCalledWith(
      "",
      "machine-a",
      expect.any(AbortSignal),
      1,
    );
    expect(previewWorkspaceFile).toHaveBeenCalledWith(
      "models/report.txt",
      0,
      200,
      "machine-a",
      expect.any(AbortSignal),
    );
    expect(
      container
        .querySelector('[title="models"]')
        ?.getAttribute("aria-expanded"),
    ).toBe("true");
    expect(container.querySelector("[data-preview]")?.textContent).toContain(
      "hello",
    );
    await click(".workspace-root");
    expect(container.querySelector("[data-preview]")).toBeNull();
    expect(container.textContent).toContain("workspace.select");
  });

  it("appends more entries and loads folders only when opened", async () => {
    vi.mocked(listWorkspaceEntries).mockImplementation(
      async (path, _target, _signal, offset) => {
        if (path === "agents") return directory(path);
        return offset
          ? directory("", [entry("models")])
          : directory("", [entry("agents")], true);
      },
    );
    await render();
    expect(listWorkspaceEntries).toHaveBeenCalledTimes(1);
    await click(".workspace-tree-more");
    expect(container.querySelector('[title="agents"]')).not.toBeNull();
    expect(container.querySelector('[title="models"]')).not.toBeNull();
    expect(container.querySelector(".workspace-tree-more")).toBeNull();
    await click('[title="agents"]');
    expect(container.textContent).toContain("workspace.empty");
    await click('[title="agents"]');
    expect(
      container
        .querySelector('[title="agents"]')
        ?.getAttribute("aria-expanded"),
    ).toBe("false");
    await click('[title="agents"]');
    expect(listWorkspaceEntries).toHaveBeenCalledTimes(3);
  });

  it("displays directory failures and retries from the root", async () => {
    vi.mocked(listWorkspaceEntries).mockRejectedValueOnce(new Error("offline"));
    await render();
    expect(container.textContent).toContain("offline");
    await click('[aria-label="refresh"]');
    expect(container.querySelector(".error-banner")).toBeNull();
    expect(container.textContent).toContain("workspace.empty");
  });

  it("blocks links and reports missing paths", async () => {
    vi.mocked(listWorkspaceEntries).mockResolvedValue(
      directory("", [entry("link", "symlink")]),
    );
    await render("missing");
    expect(container.textContent).toContain("workspace.pathUnavailable");
    expect(
      container.querySelector<HTMLButtonElement>('[title="link"]')?.disabled,
    ).toBe(true);
    expect(previewWorkspaceFile).not.toHaveBeenCalled();
  });

  it("aborts obsolete previews and ignores their results", async () => {
    const pending = deferred<WorkspacePreview>();
    vi.mocked(listWorkspaceEntries).mockResolvedValue(
      directory("", [entry("note.txt", "file")]),
    );
    vi.mocked(previewWorkspaceFile).mockReturnValue(pending.promise);
    await render("note.txt");
    const signal = vi.mocked(previewWorkspaceFile).mock.calls[0][4]!;
    await click(".workspace-root");
    expect(signal.aborted).toBe(true);
    onConnection.mockClear();
    await act(async () =>
      pending.resolve({
        kind: "text",
        content: "obsolete",
        size: 8,
        truncated: false,
      }),
    );
    expect(container.textContent).not.toContain("obsolete");
    expect(onConnection).not.toHaveBeenCalled();
  });

  it("aborts old machine listings and starts with an empty cache", async () => {
    const pending = deferred<WorkspaceDirectory>();
    vi.mocked(listWorkspaceEntries).mockReturnValueOnce(pending.promise);
    await render();
    const signal = vi.mocked(listWorkspaceEntries).mock.calls[0][2]!;
    await render(undefined, "machine-b");
    expect(signal.aborted).toBe(true);
    expect(listWorkspaceEntries).toHaveBeenLastCalledWith(
      "",
      "machine-b",
      expect.any(AbortSignal),
      0,
    );
    await act(async () => pending.resolve(directory("", [entry("obsolete")])));
    expect(container.querySelector('[title="obsolete"]')).toBeNull();
  });
});
