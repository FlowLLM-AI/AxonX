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

  it("defaults to English even when the browser uses Chinese", async () => {
    vi.stubGlobal("navigator", { language: "zh-CN" });
    const i18n = await freshI18n();
    expect(i18n.resolvedLanguage).toBe("en");
  });

  it("falls back to English for unsupported browser languages", async () => {
    vi.stubGlobal("navigator", { language: "fr-FR" });
    const i18n = await freshI18n();
    expect(i18n.resolvedLanguage).toBe("en");
  });

  it("gives an explicit URL language priority over the saved language", async () => {
    localStorage.setItem("language", "en");
    vi.stubGlobal("window", { location: { search: "?lang=zh" } });
    const i18n = await freshI18n();
    expect(i18n.resolvedLanguage).toBe("zh");
  });

  it("persists both language choices and updates the URL and document", async () => {
    const replaceState = vi.fn();
    vi.stubGlobal("window", {
      location: {
        search: "?lang=en",
        href: "https://studio.example/?lang=en#local/home/overview",
      },
      history: { replaceState },
    });
    vi.stubGlobal("document", { documentElement: { lang: "en" } });
    const i18n = await freshI18n();
    const { changeLanguage } = await import("./i18n");

    for (const language of ["zh", "en"] as const) {
      await changeLanguage(language);
      expect(i18n.resolvedLanguage).toBe(language);
      expect(localStorage.getItem("language")).toBe(language);
      expect(document.documentElement.lang).toBe(
        language === "zh" ? "zh-CN" : "en",
      );
      const url = replaceState.mock.lastCall?.[2] as URL;
      expect(url.searchParams.get("lang")).toBe(language);
      expect(url.hash).toBe("#local/home/overview");
    }
  });
});
