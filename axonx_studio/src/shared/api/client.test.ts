import { afterEach, describe, expect, it, vi } from "vitest";
import { AxonXClient, AxonXError } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("AxonXClient", () => {
  it("sends target selection to the local backend", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ answer: 42, success: true, metadata: {} }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    const client = new AxonXClient();
    await expect(
      client.invoke("demo", { value: 1 }, { target: "10.0.0.2:1024" }),
    ).resolves.toBe(42);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/jobs/demo");
    expect(JSON.parse(String(init.body))).toEqual({
      arguments: { value: 1 },
      target: "10.0.0.2:1024",
    });
  });

  it("reports FastAPI error details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Unknown job" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    const client = new AxonXClient();
    await expect(client.invoke("missing")).rejects.toEqual(
      new AxonXError("Unknown job", 404),
    );
  });

  it("uses only the local token for remote jobs and catalog requests", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ answer: { items: [], total: 0 }, success: true }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = new AxonXClient();
    client.setToken("local-secret");
    await client.invoke("status", {}, { target: "http://remote.test:1024" });
    await client.jobs({ target: "http://remote.test:1024" });
    expect(fetchMock.mock.calls[0][0]).toBe("/jobs/status");
    expect(fetchMock.mock.calls[1][0]).toBe(
      "/jobs?target=http%3A%2F%2Fremote.test%3A1024",
    );
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init.headers).get("Authorization")).toBe(
        "Bearer local-secret",
      );
    }
    client.setToken("");
  });

  it("restores, replaces, and clears the persisted token", () => {
    const values = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });

    const client = new AxonXClient();
    client.setToken("first");
    expect(new AxonXClient().requestHeaders().get("Authorization")).toBe(
      "Bearer first",
    );

    client.setToken("second");
    expect(new AxonXClient().requestHeaders().get("Authorization")).toBe(
      "Bearer second",
    );

    client.setToken("");
    expect(new AxonXClient().hasToken()).toBe(false);
  });
});
