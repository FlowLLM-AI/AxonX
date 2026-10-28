// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import type { JsonlPreview } from "../../shared/api/contracts";
import { FilePreview } from "./FilePreview";

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
