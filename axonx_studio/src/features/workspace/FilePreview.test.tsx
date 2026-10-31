// @vitest-environment jsdom
import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { JsonlPreview, MarkdownPreview } from "../../shared/api/contracts";
import { FilePreview } from "./FilePreview";

beforeEach(() => vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true));
afterEach(() => vi.unstubAllGlobals());

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({
    t: (key: string, options?: { line?: number }) =>
      options?.line ? `${key} ${options.line}` : key,
  }),
}));

const preview: JsonlPreview = {
  kind: "jsonl",
  size: 100,
  offset: 2,
  limit: 2,
  has_more: true,
  truncated: false,
  rows: [
    {
      line: 3,
      truncated: false,
      content: '{"percentage":50}',
      data: { percentage: 50 },
      parse_error: null,
    },
    {
      line: 4,
      truncated: false,
      content: "{broken",
      data: null,
      parse_error: "Expected property name",
    },
  ],
};

describe("JSONL file preview", () => {
  it("renders parsed records and malformed lines, and returns to the actual previous page and advances by physical line", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const onPage = vi.fn();
    try {
      await act(async () =>
        root.render(
          <FilePreview preview={preview} onPage={onPage} previousOffset={1} />,
        ),
      );
      expect(container.textContent).toContain("workspacePreview.line 3");
      expect(container.textContent).toContain("percentage");
      expect(container.textContent).toContain("50");
      expect(container.textContent).toContain("{broken");
      expect(container.textContent).toContain("Expected property name");
      expect(
        [...container.querySelectorAll<HTMLDetailsElement>("details")].map(
          (record) => record.open,
        ),
      ).toEqual([true, false]);
      const buttons = Array.from(container.querySelectorAll("footer button"));
      await act(async () => (buttons[0] as HTMLButtonElement).click());
      expect(onPage).toHaveBeenLastCalledWith(1);
      await act(async () => (buttons[1] as HTMLButtonElement).click());
      expect(onPage).toHaveBeenLastCalledWith(4);
      await act(async () =>
        root.render(
          <FilePreview
            preview={{
              ...preview,
              truncated: true,
              rows: [
                {
                  line: 5,
                  content: '{"predictions":[',
                  data: null,
                  parse_error: null,
                  truncated: true,
                },
              ],
            }}
            onPage={onPage}
            previousOffset={1}
          />,
        ),
      );
      expect(container.textContent).toContain("workspacePreview.truncated");
      expect(container.querySelector("details")?.open).toBe(true);
      expect(container.textContent).not.toContain(
        "workspacePreview.invalidJson",
      );
      await act(async () =>
        root.render(
          <FilePreview
            preview={{ ...preview, rows: [], offset: 0, has_more: false }}
            onPage={onPage}
            previousOffset={0}
          />,
        ),
      );
      expect(container.textContent).toContain("workspacePreview.emptyJsonl");
      expect(
        Array.from(container.querySelectorAll("footer button")).every(
          (button) => (button as HTMLButtonElement).disabled,
        ),
      ).toBe(true);
    } finally {
      await act(async () => root.unmount());
    }
  });
});

const markdown: MarkdownPreview = {
  kind: "markdown",
  size: 100,
  truncated: false,
  content: "# Experiment\n\n| A | B |\n| - | - |\n| 1 | 2 |",
  frontmatter: { title: "Example", tags: ["research", "demo"], seed: 42 },
  frontmatter_error: null,
};

describe("Markdown file preview", () => {
  it("resolves file links within the current workspace and keeps external links separate", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      await act(async () =>
        root.render(
          <FilePreview
            path="experiments/report/RESULTS.md"
            machineId="remote:research"
            preview={{
              ...markdown,
              content:
                "[中文](RESULTS_ZH.md)\n\n[Parent](../说明%20a.md)\n\n[External](https://example.com/report)\n\n[Mail](mailto:research@example.com)",
            }}
            onPage={() => {}}
            previousOffset={0}
          />,
        ),
      );
      const links = [...container.querySelectorAll("a")];
      expect(links[0].getAttribute("href")).toBe(
        "#remote:research/workspace/files/experiments%2Freport%2FRESULTS_ZH.md",
      );
      expect(links[1].getAttribute("href")).toBe(
        "#remote:research/workspace/files/experiments%2F%E8%AF%B4%E6%98%8E%20a.md",
      );
      expect(links[0].hasAttribute("target")).toBe(false);
      expect(links[2].getAttribute("href")).toBe("https://example.com/report");
      expect(links[2].target).toBe("_blank");
      expect(links[3].getAttribute("href")).toBe("mailto:research@example.com");
    } finally {
      await act(async () => root.unmount());
    }
  });

  it("scrolls to Markdown headings without replacing the application hash route", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    try {
      await act(async () =>
        root.render(
          <StrictMode>
            <FilePreview
              preview={{
                ...markdown,
                content:
                  "[Section](#configuration-and-coverage)\n\n[中文](#%E9%85%8D%E7%BD%AE)\n\n## Configuration and **coverage**\n\n## 配置\n\n## 配置",
              }}
              onPage={() => {}}
              previousOffset={0}
            />
          </StrictMode>,
        ),
      );
      const headings = [...container.querySelectorAll("h2")];
      expect(headings.map((heading) => heading.id)).toEqual([
        "configuration-and-coverage",
        "配置",
        "配置-1",
      ]);
      for (const [index, link] of [
        ...container.querySelectorAll("a"),
      ].entries()) {
        const scroll = vi.fn();
        headings[index].scrollIntoView = scroll;
        const event = new MouseEvent("click", {
          bubbles: true,
          cancelable: true,
        });
        await act(async () => link.dispatchEvent(event));
        expect(event.defaultPrevented).toBe(true);
        expect(scroll).toHaveBeenCalledWith({ block: "start" });
      }
    } finally {
      await act(async () => root.unmount());
    }
  });

  it("cancels an obsolete source read when switching files and ignores its late result", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    let finish!: (data: { content: string; truncated: boolean }) => void;
    const read = vi.fn<
      (signal: AbortSignal) => Promise<{ content: string; truncated: boolean }>
    >(
      () =>
        new Promise<{ content: string; truncated: boolean }>((resolve) => {
          finish = resolve;
        }),
    );
    try {
      await act(async () =>
        root.render(
          <FilePreview
            key="first"
            preview={markdown}
            onReadSource={read}
            onPage={() => {}}
            previousOffset={0}
          />,
        ),
      );
      await act(async () =>
        [...container.querySelectorAll("button")]
          .find((button) => button.textContent === "workspacePreview.source")!
          .click(),
      );
      const signal = read.mock.calls[0][0];
      await act(async () =>
        root.render(
          <FilePreview
            key="second"
            preview={{ ...markdown, content: "# Second file" }}
            onReadSource={read}
            onPage={() => {}}
            previousOffset={0}
          />,
        ),
      );
      expect(signal.aborted).toBe(true);
      await act(async () =>
        finish({ content: "OLD SOURCE", truncated: false }),
      );
      expect(container.querySelector("h1")?.textContent).toBe("Second file");
      expect(container.textContent).not.toContain("OLD SOURCE");
    } finally {
      await act(async () => root.unmount());
    }
  });
  it("renders metadata and Markdown, and lazily switches to the unchanged original source", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const content =
      '---\r\ntitle: "Example" # keep comment\r\n---\r\n# Experiment\r\n';
    const read = vi.fn().mockResolvedValue({ content, truncated: false });
    const button = (text: string) =>
      [...container.querySelectorAll("button")].find(
        (button) => button.textContent === text,
      )!;
    try {
      await act(async () =>
        root.render(
          <FilePreview
            preview={markdown}
            onReadSource={read}
            onPage={() => {}}
            previousOffset={0}
          />,
        ),
      );
      expect(container.querySelector("h1")?.textContent).toBe("Experiment");
      expect(container.querySelector("table")).not.toBeNull();
      expect(
        container.querySelector(".workspace-frontmatter .structured-tree")
          ?.textContent,
      ).toContain("42");
      expect(read).not.toHaveBeenCalled();
      await act(async () => button("workspacePreview.source").click());
      expect(container.querySelector("pre")?.textContent).toBe(content);
      expect(container.querySelector("h1")).toBeNull();
      await act(async () => button("workspacePreview.preview").click());
      expect(container.querySelector("h1")?.textContent).toBe("Experiment");
      await act(async () => button("workspacePreview.source").click());
      expect(read).toHaveBeenCalledTimes(1);
    } finally {
      await act(async () => root.unmount());
    }
  });

  it("reports source read failures and supports retry with a truncation notice", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    const read = vi
      .fn()
      .mockRejectedValueOnce(new Error("Read failed"))
      .mockResolvedValueOnce({ content: "---\n# prefix", truncated: true });
    const button = (text: string) =>
      [...container.querySelectorAll("button")].find(
        (button) => button.textContent === text,
      )!;
    try {
      await act(async () =>
        root.render(
          <FilePreview
            preview={{ ...markdown, frontmatter_error: "Invalid frontmatter" }}
            onReadSource={read}
            onPage={() => {}}
            previousOffset={0}
          />,
        ),
      );
      expect(container.textContent).toContain("Invalid frontmatter");
      await act(async () => button("workspacePreview.source").click());
      expect(container.querySelector('[role="alert"]')?.textContent).toContain(
        "Read failed",
      );
      await act(async () => button("retry").click());
      expect(container.querySelector("pre")?.textContent).toBe("---\n# prefix");
      expect(container.textContent).toContain("workspacePreview.truncated");
    } finally {
      await act(async () => root.unmount());
    }
  });
});
