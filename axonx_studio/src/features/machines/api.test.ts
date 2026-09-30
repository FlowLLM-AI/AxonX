import { describe, expect, it } from "vitest";
import { machineFromTargetAddress } from "./api";

describe("machineFromTargetAddress", () => {
  it("restores a direct target route while the local catalog is unavailable", () => {
    expect(machineFromTargetAddress("https://axonx.example.com:443")).toEqual({
      id: "https://axonx.example.com:443",
      address: "https://axonx.example.com:443",
      isLocal: false,
      healthy: false,
    });
    expect(machineFromTargetAddress("http://[::1]:1024")).not.toBeNull();
  });

  it("ignores routes that are not service addresses", () => {
    for (const address of [
      "local",
      "https://axonx.example.com",
      "http://axonx.example.com:0",
      "http://axonx.example.com:1024/jobs",
      "https://user:secret@axonx.example.com:443",
    ]) {
      expect(machineFromTargetAddress(address)).toBeNull();
    }
  });
});
