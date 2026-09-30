import { afterEach, describe, expect, it, vi } from "vitest";
import { AxonXClient, AxonXError } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("AxonXClient", () => {
  it("sends Job requests directly to the selected target", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ answer: 42, success: true, metadata: {} }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    const client = new AxonXClient("http://axonx.test");
    await expect(
      client.invoke("demo", { value: 1 }, { target: "10.0.0.2:1024" }),
    ).resolves.toBe(42);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://10.0.0.2:1024/jobs/demo");
    expect(JSON.parse(String(init.body))).toEqual({ arguments: { value: 1 } });
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
    const client = new AxonXClient("http://axonx.test");
    await expect(client.invoke("missing")).rejects.toEqual(
      new AxonXError("Unknown job", 404),
    );
  });

  it("does not send the local service token to another target", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ answer: { items: [] }, success: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new AxonXClient();
    expect(client.hasToken()).toBe(false);
    client.setToken("  session-secret  ");
    await client.forBaseUrl("http://remote.test").jobs();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get("Authorization")).toBeNull();
  });

  it("uses separate persisted tokens for separate targets", async () => {
    const values = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    });
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ answer: true, success: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new AxonXClient();
    client.setToken("local-secret");
    client.forTarget("http://one.test:1024").setToken("first-secret");
    client.forTarget("http://two.test:1024").setToken("second-secret");
    await client.invoke("status", {}, { target: "http://one.test:1024" });
    await client.invoke("status", {}, { target: "http://two.test:1024" });

    const first = fetchMock.mock.calls[0][1] as RequestInit;
    const second = fetchMock.mock.calls[1][1] as RequestInit;
    expect(new Headers(first.headers).get("Authorization")).toBe(
      "Bearer first-secret",
    );
    expect(new Headers(second.headers).get("Authorization")).toBe(
      "Bearer second-secret",
    );
    expect(new AxonXClient().requestHeaders().get("Authorization")).toBe(
      "Bearer local-secret",
    );
    client.forTarget("http://one.test:1024").setToken("");
    expect(client.forTarget("http://one.test:1024").hasToken()).toBe(false);
    expect(client.forTarget("http://two.test:1024").hasToken()).toBe(true);
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
