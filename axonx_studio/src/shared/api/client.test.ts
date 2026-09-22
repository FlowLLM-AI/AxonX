import { afterEach, describe, expect, it, vi } from "vitest";
import { AxonXClient, AxonXError } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("AxonXClient", () => {
  it("keeps remote targeting outside business arguments", async () => {
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
      client.invoke("demo", { value: 1 }, { remoteIp: "10.0.0.2" }),
    ).resolves.toBe(42);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      arguments: { value: 1 },
      remote_ip: "10.0.0.2",
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
    const client = new AxonXClient("http://axonx.test");
    await expect(client.invoke("missing")).rejects.toEqual(
      new AxonXError("Unknown job", 404),
    );
  });

  it("adds only a runtime-provided token to requests and derived clients", async () => {
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
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer session-secret",
    );
  });
});
