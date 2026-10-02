import assert from "node:assert/strict";
import { readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const site = fileURLToPath(new URL("../dist/", import.meta.url));
const map = JSON.parse(
  await readFile(
    new URL("../.generated/site/.source-map.json", import.meta.url),
    "utf8",
  ),
);
const base = process.env.DOCS_BASE || "/AxonX/";
const exists = async (file) =>
  assert(
    (await stat(site + file)).size > 0,
    `Missing or empty output: ${file}`,
  );
const pages = [
  "index.html",
  "zh/index.html",
  "en/index.html",
  ...Object.keys(map).map((page) => page.replace(/\.md$/, ".html")),
];
const groupFor = (page) => {
  if (["getting-started/studio", "development/studio"].includes(page))
    return "studio";
  if (page.startsWith("research/")) return "research";
  if (page.startsWith("agent/") || page === "api/agent") return "agent";
  if (
    /^(api|development)\//.test(page) ||
    page === "dev_guide" ||
    /^reference\/(python|task-contracts|plugin-manifest|research-artifacts)$/.test(
      page,
    )
  )
    return "developers";
  return "docs";
};
const groupPages = Object.keys(map).map((page) => page.replace(/\.md$/, ""));
const checked = new Set();

for (const file of [...pages, "axonx-icon.svg", "llms.txt", "llms-full.txt"])
  await exists(file);
for (const file of ["llms.txt", "llms-full.txt", ...Object.keys(map)]) {
  const bytes = await readFile(site + file);
  assert(
    bytes.subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf])),
    `Missing UTF-8 marker: ${file}`,
  );
  new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}
for (const page of pages) {
  const html = await readFile(site + page, "utf8");
  for (const [, href] of html.matchAll(/(?:href|src)="([^"]+)"/g)) {
    const url = new URL(
      href.replaceAll("&amp;", "&"),
      `https://site.test${base}${page}`,
    );
    if (url.origin !== "https://site.test") continue;
    assert(
      url.pathname.startsWith(base),
      `Link escapes deployment base in ${page}: ${href}`,
    );
    let target = decodeURIComponent(url.pathname.slice(base.length));
    if (target.endsWith("/") || !target) target += "index.html";
    else if (!/\.[^/]+$/.test(target)) target += ".html";
    if (!checked.has(target)) {
      await exists(target);
      checked.add(target);
    }
  }
  if (map[page.replace(/\.html$/, ".md")]) {
    const route = page.replace(/\.html$/, "");
    const [lang, ...parts] = route.split("/");
    const group = groupFor(parts.join("/"));
    const sidebar = html.match(
      /<aside class="VPSidebar"[\s\S]*?<\/aside>/,
    )?.[0];
    assert(sidebar, `Missing group sidebar: ${page}`);
    const links = [...sidebar.matchAll(/href="([^"#]+)"/g)].map(([, href]) =>
      href.slice(base.length),
    );
    const expected = groupPages.filter(
      (route) =>
        route.startsWith(`${lang}/`) && groupFor(route.slice(3)) === group,
    );
    assert.deepEqual(
      links.sort(),
      expected.sort(),
      `Incorrect group directory: ${page}`,
    );
    const active = [
      ...html.matchAll(/<a class="[^"]*VPNavBarMenuLink active"[^>]*>/g),
    ];
    assert.equal(
      active.length,
      1,
      `Expected one active navigation tab: ${page}`,
    );
    const original = map[page.replace(/\.html$/, ".md")];
    assert(
      html.includes(`github.com/FlowLLM-AI/AxonX/edit/main/${original}`),
      `Incorrect edit link: ${page}`,
    );
  }
}
const cn = await readFile(site + "zh/index.html", "utf8");
const en = await readFile(site + "en/index.html", "utf8");
assert(cn.includes("可追踪的闭环"), "Chinese homepage was not rendered");
assert(
  en.includes("Connected. Traceable."),
  "English homepage was not rendered",
);
assert(
  !cn.includes('class="VPSidebar"'),
  "Homepage should use the full canvas",
);
const languages = ["zh", "en"].map((lang) =>
  Object.keys(map)
    .filter((page) => page.startsWith(`${lang}/`))
    .map((page) => page.slice(3))
    .sort(),
);
assert.deepEqual(
  ...languages,
  "Documentation translations must have matching paths",
);
console.log(
  `Verified ${Object.keys(map).length} guides, bilingual homepages, ${
    checked.size
  } local links/assets, grouped navigation, source links, and Markdown exports.`,
);
