import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { groups, groupRoutes } from "../../docs/.vitepress/navigation.mjs";

import { documentTitle, importedTitles } from "./headings.mjs";

export const languages = ["en", "zh"];
export const repository = "https://github.com/FlowLLM-AI/AxonX";
export const published = "https://flowllm-ai.github.io/AxonX/";
export const importedPages = {
  "getting-started/overview": "README{suffix}.md",
  "development/contributing": "CONTRIBUTING{suffix}.md",
  "plugins/qlib-a158": "plugins/qlib_a158/README{suffix}.md",
  "plugins/qlib-strategy": "plugins/qlib_strategy/README{suffix}.md",
  "plugins/qlib-factor": "plugins/qlib_factor/README{suffix}.md",
};

async function markdownFiles(directory, prefix = "") {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const relative = `${prefix}${entry.name}`;
    if (entry.isDirectory())
      files.push(
        ...(await markdownFiles(
          path.join(directory, entry.name),
          `${relative}/`,
        )),
      );
    else if (entry.name.endsWith(".md")) files.push(relative);
  }
  return files.sort();
}

// Validate bilingual sources and navigation before changing generated output.
export async function contentCatalog(root) {
  const owners = new Map();
  for (const group of groups) {
    assert(
      groupRoutes(group).includes(group.page),
      `Group landing page is not owned: ${group.id}`,
    );
    for (const route of groupRoutes(group)) {
      assert(!owners.has(route), `Multiple navigation owners: ${route}`);
      owners.set(route, group.id);
    }
  }
  const files = await Promise.all(
    languages.map((lang) => markdownFiles(path.join(root, "docs", lang))),
  );
  assert.deepEqual(
    files[0],
    files[1],
    "English and Chinese documentation must have matching paths",
  );
  const sources = {};
  for (const lang of languages) {
    const suffix = lang === "zh" ? "_ZH" : "";
    const available = new Map(
      files[0].map((file) => [
        file === "index.md" ? "docs" : file.slice(0, -3),
        `docs/${lang}/${file}`,
      ]),
    );
    for (const [route, source] of Object.entries(importedPages)) {
      assert(
        !available.has(route),
        `Imported route collides with a document: ${route}`,
      );
      available.set(route, source.replace("{suffix}", suffix));
    }
    assert.deepEqual(
      [...available.keys()].sort(),
      [...owners.keys()].sort(),
      "Every source must have exactly one navigation owner",
    );
    for (const route of owners.keys()) {
      const original = available.get(route);
      const content = await readFile(path.join(root, original), "utf8");
      assert(
        documentTitle(content) || importedTitles[route]?.[lang],
        `Missing document heading: ${original}`,
      );
      sources[`${lang}/${route}.md`] = original;
    }
  }
  return sources;
}
