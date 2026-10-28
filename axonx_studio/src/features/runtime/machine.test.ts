import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AxonXClient,
  configureClient,
  type Transport,
} from "../../shared/api/client";
import { listMachineOptions, machineStatus } from "./machine";

afterEach(() => {
  vi.unstubAllGlobals();
  configureClient(new AxonXClient());
});

const response = () =>
  Response.json({ success: true, answer: { axonx: { version: "1.0" } } });

describe("machineStatus", () => {
  it("merges concurrent reads and fetches a fresh snapshot after completion", async () => {
    const transport = vi.fn(async () => response());
    configureClient(new AxonXClient(transport, false));
    const [first, second] = await Promise.all([
      machineStatus(),
      machineStatus(),
    ]);
    expect(first).toBe(second);
    expect(transport).toHaveBeenCalledOnce();
    await machineStatus();
    expect(transport).toHaveBeenCalledTimes(2);
  });

  it("lets one subscriber cancel without aborting another subscriber", async () => {
    let finish!: (response: Response) => void;
    const transport = vi.fn<Transport>(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    );
    configureClient(new AxonXClient(transport, false));
    const controller = new AbortController();
    const first = machineStatus({
      target: "remote",
      signal: controller.signal,
    });
    const second = machineStatus({ target: "remote" });
    const rejected = expect(first).rejects.toMatchObject({
      name: "AbortError",
    });
    controller.abort();
    await rejected;
    expect(transport).toHaveBeenCalledOnce();
    expect(transport.mock.calls[0][1]?.signal?.aborted).toBe(false);
    finish(response());
    await expect(second).resolves.toMatchObject({ axonx: { version: "1.0" } });
  });

  it("aborts the transport when all subscribers cancel and permits an immediate retry", async () => {
    const transport = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init!.signal!.addEventListener(
            "abort",
            () => reject(init!.signal!.reason),
            { once: true },
          );
        }),
    );
    configureClient(new AxonXClient(transport, false));
    const firstController = new AbortController();
    const secondController = new AbortController();
    const first = machineStatus({ signal: firstController.signal });
    const second = machineStatus({ signal: secondController.signal });
    const rejected = Promise.all([
      expect(first).rejects.toMatchObject({ name: "AbortError" }),
      expect(second).rejects.toMatchObject({ name: "AbortError" }),
    ]);
    firstController.abort();
    expect(transport.mock.calls[0][1]?.signal?.aborted).toBe(false);
    secondController.abort();
    expect(transport.mock.calls[0][1]?.signal?.aborted).toBe(true);
    transport.mockImplementationOnce(async () => response());
    const retry = machineStatus();
    await rejected;
    await expect(retry).resolves.toMatchObject({ axonx: { version: "1.0" } });
    expect(transport).toHaveBeenCalledTimes(2);
  });

  it("isolates requests by target, authentication revision, and client", async () => {
    const transport = vi.fn<Transport>(async () => response());
    const client = new AxonXClient(transport);
    configureClient(client);
    const local = machineStatus();
    const remote = machineStatus({ target: "remote" });
    client.setToken("first");
    const authenticated = machineStatus();
    client.setToken(" first ");
    const sameToken = machineStatus();
    client.setToken("");
    const cleared = machineStatus();
    configureClient(new AxonXClient(transport, false));
    const replacement = machineStatus();
    await Promise.all([
      local,
      remote,
      authenticated,
      sameToken,
      cleared,
      replacement,
    ]);
    expect(transport).toHaveBeenCalledTimes(5);
    expect(
      new Headers(transport.mock.calls[2]?.[1]?.headers).get("Authorization"),
    ).toBe("Bearer first");
    expect(
      new Headers(transport.mock.calls[3]?.[1]?.headers).has("Authorization"),
    ).toBe(false);
  });

  it("does not start cancelled reads and retries failed reads", async () => {
    const transport = vi.fn<Transport>(async () => response());
    transport.mockRejectedValueOnce(new Error("Offline"));
    configureClient(new AxonXClient(transport, false));
    const controller = new AbortController();
    controller.abort();
    await expect(
      machineStatus({ signal: controller.signal }),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(transport).not.toHaveBeenCalled();
    await expect(machineStatus()).rejects.toThrow("Offline");
    await expect(machineStatus()).resolves.toMatchObject({
      axonx: { version: "1.0" },
    });
    expect(transport).toHaveBeenCalledTimes(2);
  });
});

describe("listMachineOptions", () => {
  it("uses configured addresses without reconstructing target protocols", async () => {
    vi.stubGlobal("window", { location: { host: "localhost:4173" } });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          success: true,
          answer: [
            { address: "http://11.160.132.45:1024", healthy: true },
            { address: "https://axonx.example.com:443", healthy: false },
          ],
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    expect(await listMachineOptions()).toEqual([
      { id: "local", address: "localhost:4173", isLocal: true, healthy: true },
      {
        id: "11.160.132.45:1024",
        address: "http://11.160.132.45:1024",
        isLocal: false,
        healthy: true,
      },
      {
        id: "https://axonx.example.com:443",
        address: "https://axonx.example.com:443",
        isLocal: false,
        healthy: false,
      },
    ]);
    expect(fetchMock.mock.calls[0][0]).toBe("/jobs/list_machines");
  });
});
