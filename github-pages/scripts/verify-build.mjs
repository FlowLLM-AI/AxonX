import assert from "node:assert/strict";
import { groups, groupRoutes } from "../../docs/.vitepress/navigation.mjs";
import { mapLinks } from "../lib/links.mjs";
import { siteSettings } from "../lib/settings.mjs";
import { readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const site = fileURLToPath(new URL("../dist/", import.meta.url));
const map = JSON.parse(
  await readFile(
    new URL("../.generated/site/.source-map.json", import.meta.url),
    "utf8",
  ),
);
const { base, siteUrl } = siteSettings();
const exists = async (file) =>
  assert(
    (await stat(site + file)).size > 0,
    `Missing or empty output: ${file}`,
  );
const pages = [
  "index.html",
  "playground/index.html",
  "zh/index.html",
  "en/index.html",
  ...Object.keys(map).map((page) => page.replace(/\.md$/, ".html")),
];
const owners = new Map();
for (const group of groups) {
  for (const route of groupRoutes(group)) {
    assert(!owners.has(route), `Document belongs to multiple tabs: ${route}`);
    owners.set(route, group.id);
  }
}
const groupFor = (page) => {
  assert(owners.has(page), `Document has no navigation tab: ${page}`);
  return owners.get(page);
};
const groupPages = Object.keys(map).map((page) => page.replace(/\.md$/, ""));
const checked = new Set();
const anchors = new Map();
async function checkAnchor(target, hash, page) {
  if (!hash || !target.endsWith(".html")) return;
  if (!anchors.has(target)) {
    const html = await readFile(site + target, "utf8");
    anchors.set(
      target,
      new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => id)),
    );
  }
  assert(
    anchors.get(target).has(decodeURIComponent(hash.slice(1))),
    `Missing anchor in ${page}: ${target}${hash}`,
  );
}

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
for (const lang of ["en", "zh"]) {
  for (const route of owners.keys())
    assert(
      map[`${lang}/${route}.md`],
      `Navigation has no source: ${lang}/${route}`,
    );
}
for (const legacy of [
  "getting-started/introduction",
  "guides/plugin-management",
]) {
  for (const lang of ["en", "zh"]) {
    await assert.rejects(stat(`${site}${lang}/${legacy}.html`), {
      code: "ENOENT",
    });
  }
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
    await checkAnchor(target, url.hash, page);
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
for (const page of Object.keys(map)) {
  const content = await readFile(site + page, "utf8");
  const urls = [];
  mapLinks(content, (href) => {
    urls.push(href);
    return href;
  });
  const origin = siteUrl;
  for (const href of urls) {
    if (href.startsWith("#")) continue;
    assert(
      /^[a-z]+:/i.test(href),
      `Relative URL in Markdown export ${page}: ${href}`,
    );
    if (!href.startsWith(`${origin}${base}`)) continue;
    const target = new URL(href).pathname.slice(base.length);
    await exists(
      /\.[^/]+$/.test(target)
        ? target
        : target.endsWith("/")
          ? `${target}index.html`
          : `${target}.html`,
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

const playground = await readFile(site + "playground/index.html", "utf8");
assert(
  playground.includes(`${base}playground/assets/`),
  "Playground assets must respect the deployment base",
);
