import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const values = new Map<string, string>();
const storage = {
  clear: () => values.clear(),
  getItem: (key: string) => values.get(key) ?? null,
  removeItem: (key: string) => values.delete(key),
  setItem: (key: string, value: string) => values.set(key, value),
  key: (index: number) => [...values.keys()][index] ?? null,
  get length() {
    return values.size;
  },
};

async function freshI18n() {
  vi.resetModules();
  const module = await import("./i18n");
  if (!module.default.isInitialized) {
    await new Promise((resolve) => module.default.on("initialized", resolve));
  }
  return module.default;
}

describe("i18n initialization", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", storage);
    vi.stubGlobal("navigator", { language: "en-US" });
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("restores a persisted language", async () => {
    localStorage.setItem("language", "zh");
    const i18n = await freshI18n();
    expect(i18n.resolvedLanguage).toBe("zh");
  });

  it("uses the browser language when no preference exists", async () => {
    vi.stubGlobal("navigator", { language: "zh-CN" });
    const i18n = await freshI18n();
    expect(i18n.resolvedLanguage).toBe("zh");
  });

  it("falls back to English for unsupported browser languages", async () => {
    vi.stubGlobal("navigator", { language: "fr-FR" });
    const i18n = await freshI18n();
    expect(i18n.resolvedLanguage).toBe("en");
  });
});
