import { afterEach, expect, it, vi } from "vitest";
import { createPlayground } from "../../playground/runtime";
import { AxonXClient, configureClient, type Transport } from "./client";
import { readWorkspaceText } from "./workspace";

afterEach(() => configureClient(new AxonXClient()));

const answer = (bytes: Uint8Array, truncated = false) => ({
  stdout: JSON.stringify({
    data: btoa(Array.from(bytes, (byte) => String.fromCharCode(byte)).join("")),
    truncated,
  }),
  stdout_truncated: false,
});

it("reads original frontmatter, comments and line endings on the selected machine", async () => {
  const source =
    '---\r\ntitle: "报告" # keep this comment\r\n---\r\n# Report\r\n';
  const transport = vi.fn<Transport>(async () =>
    Response.json({
      success: true,
      answer: answer(new TextEncoder().encode(source)),
    }),
  );
  configureClient(new AxonXClient(transport, false));
  const signal = new AbortController().signal;
  const path = 'reports/a";print(123).md';
  expect(
    await readWorkspaceText(
      { path, workspaceRoot: "/workspace" },
      { target: "remote:1024", signal },
    ),
  ).toEqual({ content: source, truncated: false });
  const [url, init] = transport.mock.calls[0];
  expect(url).toBe("/jobs/python");
  expect(init?.signal).toBe(signal);
  const request = JSON.parse(String(init?.body));
  expect(request.target).toBe("remote:1024");
  const settings = request.arguments.code.match(
    /^settings = json.loads\((.+)\)$/m,
  );
  expect(JSON.parse(JSON.parse(settings[1]))).toEqual([
    "/workspace",
    path,
    512 * 1024,
  ]);
  expect(request.arguments.code).toContain(
    "Workspace(root).resolve_file(path)",
  );
});

it("does not render an incomplete UTF-8 character at the preview boundary", async () => {
  configureClient(
    new AxonXClient(
      async () =>
        Response.json({
          success: true,
          answer: answer(new Uint8Array([65, 0xe4, 0xb8]), true),
        }),
      false,
    ),
  );
  expect(
    await readWorkspaceText({ path: "a.md", workspaceRoot: "/workspace" }),
  ).toEqual({ content: "A", truncated: true });
});

it("rejects a truncated transport response instead of presenting it as full source", async () => {
  configureClient(
    new AxonXClient(
      async () =>
        Response.json({
          success: true,
          answer: { stdout: "", stdout_truncated: true },
        }),
      false,
    ),
  );
  await expect(
    readWorkspaceText({ path: "a.md", workspaceRoot: "/workspace" }),
  ).rejects.toThrow("truncated");
});

it("preserves a file read error as a useful message", async () => {
  configureClient(
    new AxonXClient(
      async () =>
        Response.json({
          success: true,
          answer: {
            stdout: JSON.stringify({ error: "Workspace file does not exist" }),
            stdout_truncated: false,
          },
        }),
      false,
    ),
  );
  await expect(
    readWorkspaceText({ path: "missing.md", workspaceRoot: "/workspace" }),
  ).rejects.toThrow("Workspace file does not exist");
});

it("provides original Markdown including frontmatter in Playground", async () => {
  configureClient(new AxonXClient(createPlayground(), false));
  const source = await readWorkspaceText({
    path: "tushare/README.md",
    workspaceRoot: "/demo/workspace",
  });
  expect(source.content).toContain(
    'title: "Synthetic market data" # demo metadata',
  );
  expect(source.content).toContain("合成行情");
  expect(source.truncated).toBe(false);
});
