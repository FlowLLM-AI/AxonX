import { statSync } from "node:fs";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { importedTitles } from "../lib/headings.mjs";
import { mapLinks } from "../lib/links.mjs";
import { contentCatalog, repository, published } from "../lib/site-model.mjs";
import { siteSettings } from "../lib/settings.mjs";
import { createMarkdownRenderer } from "vitepress";
import { renderReadmeHome } from "../lib/readme-home.mjs";

const root = fileURLToPath(new URL("../../", import.meta.url));
const docs = path.join(root, "docs");
const output = path.join(root, "github-pages/.generated/site");
const { base } = siteSettings();
const repositoryRoots = [
  `${repository}/blob/main/`,
  `${repository}/tree/main/`,
  "https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/",
];
const posix = (file) => file.split(path.sep).join("/");

const sourceMap = await contentCatalog(root);
const routes = new Map(
  Object.entries(sourceMap).map(([route, original]) => [
    original,
    `/${route.replace(/\.md$/, "")}`,
  ]),
);
const assets = new Map();
const homepageSources = {};

await rm(output, { recursive: true, force: true });
await cp(docs, output, {
  recursive: true,
  filter: (file) => ![".DS_Store", ".vitepress"].includes(path.basename(file)),
});
await cp(
  path.join(root, "github-pages/site/theme"),
  path.join(output, ".vitepress/theme"),
  { recursive: true },
);
// Load the canonical configuration and modules directly; only theme assets are copied.
await writeFile(
  path.join(output, ".vitepress/config.mts"),
  'export { default } from "../../../site/config.mts";\n',
);
await mkdir(path.join(output, "public"), { recursive: true });
for (const name of ["axonx-icon.svg", "axonx-logo.svg"]) {
  await cp(
    path.join(root, "axonx_studio/public", name),
    path.join(output, "public", name),
  );
}
for (const [route, original] of Object.entries(sourceMap)) {
  const resolve = (href, image) => {
    if (href.startsWith(published)) return `/${href.slice(published.length)}`;
    let local = href;
    const prefix = repositoryRoots.find((prefix) => href.startsWith(prefix));
    if (prefix) {
      local = href.slice(prefix.length);
    } else {
      if (/^(?:[a-z]+:|\/|#)/i.test(href)) return href;
      local = posix(path.join(path.dirname(original), href));
    }
    const [, pathname, suffix = ""] = local.match(/^([^?#]*)(.*)$/);
    const source = path.posix.normalize(pathname);
    if (source.startsWith("../"))
      throw new Error(`Link outside repository in ${original}: ${href}`);
    if (image) {
      const target = `media/${source}`;
      assets.set(target, source);
      return `/${target}${suffix}`;
    }
    if (routes.has(source)) return `${routes.get(source)}${suffix}`;
    const kind = statSync(path.join(root, source)).isDirectory()
      ? "tree"
      : "blob";
    return `${repository}/${kind}/main/${source}${suffix}`;
  };
  const importedTitle = importedTitles[route.slice(3, -3)]?.[route.slice(0, 2)];
  // Keep canonical sources unchanged while publishing emoji-free site content.
  const originalContent = (
    await readFile(path.join(root, original), "utf8")
  ).replace(/\p{RGI_Emoji}/gv, "");
  const content = mapLinks(
    importedTitle
      ? `# ${importedTitle}\n\n${originalContent}`
      : originalContent,
    (href, image, html) => {
      const url = resolve(href, image);
      return html && !image && url.startsWith("/")
        ? `${base}${url.slice(1)}`
        : url;
    },
  );
  await mkdir(path.dirname(path.join(output, route)), { recursive: true });
  await writeFile(path.join(output, route), content);
  if (original === "README.md" || original === "README_ZH.md") {
    homepageSources[route.slice(0, 2)] = content;
  }
}
const markdown = await createMarkdownRenderer(output, { html: true });
const homepage = Object.fromEntries(
  ["en", "zh"].map((lang) => [
    lang,
    renderReadmeHome(homepageSources[lang], markdown, {
      base,
      overview: `${lang}/getting-started/overview`,
    }),
  ]),
);
await writeFile(
  path.join(output, ".vitepress/theme/readme-home.json"),
  JSON.stringify(homepage, null, 2),
);

for (const [target, source] of assets) {
  await mkdir(path.dirname(path.join(output, "public", target)), {
    recursive: true,
  });
  await cp(path.join(root, source), path.join(output, "public", target));
}
for (const lang of ["", "zh/", "en/"]) {
  await writeFile(
    path.join(output, lang, "index.md"),
    "---\nlayout: page\nsidebar: false\ntitle: AxonX\n---\n\n<HomePage />\n",
  );
}
await rm(path.join(output, "README.md"), { force: true });
await writeFile(
  path.join(output, ".source-map.json"),
  JSON.stringify(sourceMap, null, 2),
);
console.log(
  `Prepared ${Object.keys(sourceMap).length} documentation pages and ${assets.size} shared assets.`,
);
