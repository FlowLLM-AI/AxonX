import { afterEach, describe, expect, it, vi } from "vitest";
import { listMachineOptions } from "./api";

afterEach(() => vi.unstubAllGlobals());

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
