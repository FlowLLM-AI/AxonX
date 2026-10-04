import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { initialLanguage, languageRoute } from "../site/theme/language.mjs";

const defaults = {
  relativePath: "index.md",
  search: "",
  saved: "",
  browser: "en-US",
};

test("explicit query and document languages take precedence over saved preferences", () => {
  assert.equal(
    initialLanguage({
      ...defaults,
      relativePath: "en/research/results.md",
      saved: "zh",
    }),
    "en",
  );
  assert.equal(
    initialLanguage({ ...defaults, relativePath: "zh/index.md", saved: "en" }),
    "zh",
  );
  assert.equal(
    initialLanguage({
      ...defaults,
      relativePath: "zh/index.md",
      search: "?lang=en",
      saved: "zh",
    }),
    "en",
  );
  assert.equal(
    initialLanguage({
      ...defaults,
      relativePath: "zh/index.md",
      search: "?lang=fr",
    }),
    "zh",
  );
});

test("root entry uses Studio's preference and browser fallbacks", () => {
  assert.equal(initialLanguage({ ...defaults, saved: "zh" }), "zh");
  assert.equal(
    initialLanguage({ ...defaults, saved: "en", browser: "zh-CN" }),
    "en",
  );
  assert.equal(
    initialLanguage({ ...defaults, saved: "invalid", browser: "zh-TW" }),
    "zh",
  );
  assert.equal(initialLanguage({ ...defaults, browser: "fr-FR" }), "en");
  assert.equal(
    initialLanguage({ ...defaults, search: "?lang=zh", saved: "en" }),
    "zh",
  );
});

test("language switches preserve documents, anchors, and query data without retaining a conflicting lang", () => {
  assert.equal(
    languageRoute(
      "en/research/results.md",
      "zh",
      "?lang=en&query=a%26b",
      "#training",
    ),
    "/zh/research/results?lang=zh&query=a%26b#training",
  );
  assert.equal(languageRoute("zh/index.md", "en"), "/en/");
  assert.equal(languageRoute("index.md", "zh"), "/zh/");
  assert.equal(
    languageRoute("en/guide/index.md", "zh", "?q=demo"),
    "/zh/guide/?q=demo",
  );
});

function keys(value, prefix = "") {
  return Object.entries(value)
    .flatMap(([key, child]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      if (typeof child === "object") return keys(child, path);
      assert.equal(typeof child, "string", `Invalid translation: ${path}`);
      assert(child.trim(), `Empty translation: ${path}`);
      return [path];
    })
    .sort();
}

test("English and Chinese resources have matching nonempty translation keys", async () => {
  const [en, zh] = await Promise.all(
    ["en", "zh"].map(async (lang) =>
      JSON.parse(
        await readFile(
          new URL(`../site/theme/locales/${lang}.json`, import.meta.url),
          "utf8",
        ),
      ),
    ),
  );
  assert.deepEqual(keys(en), keys(zh));
});
