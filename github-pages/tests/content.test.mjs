import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { contentCatalog, importedPages } from "../lib/site-model.mjs";
import { siteSettings } from "../lib/settings.mjs";
import { documentTitle } from "../lib/headings.mjs";
import { mapLinks } from "../lib/links.mjs";
import { groups, groupRoutes } from "../../docs/.vitepress/navigation.mjs";

const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));

async function fixture(t) {
  const root = await mkdtemp(path.join(os.tmpdir(), "axonx-docs-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  for (const lang of ["en", "zh"]) {
    for (const route of groups.flatMap(groupRoutes)) {
      const relative =
        importedPages[route]?.replace("{suffix}", lang === "zh" ? "_ZH" : "") ||
        `docs/${lang}/${route === "docs" ? "index" : route}.md`;
      const file = path.join(root, relative);
      await mkdir(path.dirname(file), { recursive: true });
      await writeFile(file, `# ${route}\n`);
    }
  }
  return root;
}

test("catalog follows navigation order and preserves canonical imported sources", async () => {
  const catalog = await contentCatalog(repositoryRoot);
  const ordered = groups.flatMap(groupRoutes);
  assert.deepEqual(
    Object.keys(catalog),
    ["en", "zh"].flatMap((lang) =>
      ordered.map((route) => `${lang}/${route}.md`),
    ),
  );
  assert.equal(catalog["zh/getting-started/overview.md"], "README_ZH.md");
  assert.equal(catalog["en/agent/external.md"], "docs/en/agent/external.md");
});

test("catalog rejects missing translations and unowned bilingual pages", async (t) => {
  const root = await fixture(t);
  await writeFile(path.join(root, "docs/en/orphan.md"), "# Orphan\n");
  await assert.rejects(contentCatalog(root), /matching paths/);
  await writeFile(path.join(root, "docs/zh/orphan.md"), "# Orphan\n");
  await assert.rejects(contentCatalog(root), /navigation owner/);
});

test("catalog rejects missing headings before generation", async (t) => {
  const root = await fixture(t);
  await writeFile(path.join(root, "docs/en/agent/external.md"), "No heading\n");
  await assert.rejects(contentCatalog(root), /Missing document heading/);
});

test("deployment settings accept root and nested mounts and reject ambiguous origins", () => {
  assert.deepEqual(
    siteSettings({
      DOCS_BASE: "/",
      DOCS_SITE_URL: "https://docs.example.com/",
    }),
    { base: "/", siteUrl: "https://docs.example.com" },
  );
  assert.equal(
    siteSettings({ DOCS_BASE: "/research/docs/" }).base,
    "/research/docs/",
  );
  for (const base of ["AxonX/", "/AxonX", "/../", "/x?y/"])
    assert.throws(() => siteSettings({ DOCS_BASE: base }));
  for (const origin of [
    "file:///tmp/",
    "https://docs.example.com/path",
    "https://user@docs.example.com",
    "https://docs.example.com/?query=1",
  ])
    assert.throws(() => siteSettings({ DOCS_SITE_URL: origin }));
});

test("link conversion preserves fenced examples while transforming Markdown and HTML", () => {
  const source =
    '[Guide](guide.md)\n<a\n href="guide.md">Guide</a>\n```md\n[Example](guide.md)\n```\n';
  assert.equal(
    mapLinks(source, (href) => `/en/${href}`),
    '[Guide](/en/guide.md)\n<a\n href="/en/guide.md">Guide</a>\n```md\n[Example](guide.md)\n```\n',
  );
});

test("document titles exclude fenced shell comments and nested Markdown examples", () => {
  assert.equal(
    documentTitle("```sh\n# Token configuration\n```\n## Details\n"),
    undefined,
  );
  assert.equal(
    documentTitle("~~~md\n# Example\n~~~\n# Real title ###\n"),
    "Real title",
  );
  assert.equal(
    documentTitle("````md\n```\n# Example\n```\n````\n# Real title\n"),
    "Real title",
  );
});

test("catalog rejects a code comment masquerading as a document heading", async (t) => {
  const root = await fixture(t);
  await writeFile(
    path.join(root, "docs/en/agent/external.md"),
    "```sh\n# A comment\n```\n",
  );
  await assert.rejects(contentCatalog(root), /Missing document heading/);
});

test("link conversion respects nested, indented, and unclosed code fences", () => {
  for (const source of [
    "````md\n```\n[Example](guide.md)\n```\n````\n",
    "  ~~~~md\n[Example](guide.md)\n  ~~~\n[Still an example](guide.md)\n  ~~~~~\n",
    "```md\n[Example](guide.md)\n",
  ]) {
    assert.equal(
      mapLinks(source, (href) => `/converted/${href}`),
      source,
    );
  }
  const source =
    "````md\n```\n[Example](guide.md)\n```\n````\n[Real](guide.md)\n";
  assert.equal(
    mapLinks(source, (href) => `/converted/${href}`),
    source.replace("[Real](guide.md)", "[Real](/converted/guide.md)"),
  );
});
