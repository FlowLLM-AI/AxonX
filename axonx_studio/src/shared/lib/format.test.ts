import { describe, expect, it } from "vitest";
import { formatBytes, formatDateTime } from "./format";

describe("format utilities", () => {
  it("formats binary byte sizes", () => {
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1536)).toBe("1.5 KiB");
  });

  it("formats absent dates safely", () => {
    expect(formatDateTime(null, "zh")).toBe("—");
  });
});
