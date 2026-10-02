import { describe, expect, it } from "vitest";
import { machineFromTargetAddress } from "./api";

describe("machineFromTargetAddress", () => {
  it("restores a direct target route while the local catalog is unavailable", () => {
    expect(machineFromTargetAddress("11.160.132.45:1024")).toEqual({
      id: "11.160.132.45:1024",
      address: "http://11.160.132.45:1024",
      isLocal: false,
      healthy: false,
    });
    expect(machineFromTargetAddress("https://axonx.example.com:443")).toEqual({
      id: "https://axonx.example.com:443",
      address: "https://axonx.example.com:443",
      isLocal: false,
      healthy: false,
    });
    expect(machineFromTargetAddress("[::1]:1024")).not.toBeNull();
  });

  it("ignores routes that are not service addresses", () => {
    for (const address of [
      "local",
      "http://axonx.example.com:1024",
      "https://axonx.example.com",
      "axonx.example.com:0",
      "axonx.example.com:1024/jobs",
      "https://user:secret@axonx.example.com:443",
    ]) {
      expect(machineFromTargetAddress(address)).toBeNull();
    }
  });
});
