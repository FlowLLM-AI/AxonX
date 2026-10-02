import { statSync } from "node:fs";
import { cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { mapLinks } from "../../docs/.vitepress/links.mjs";

const root = fileURLToPath(new URL("../../", import.meta.url));
const docs = path.join(root, "docs");
const output = path.join(root, "github-pages/.generated/site");
const repository = "https://github.com/FlowLLM-AI/AxonX";
const base = process.env.DOCS_BASE || "/AxonX/";
const published = "https://flowllm-ai.github.io/AxonX/";
const repositoryRoots = [
  `${repository}/blob/main/`,
  `${repository}/tree/main/`,
  "https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/",
];
const posix = (file) => file.split(path.sep).join("/");

async function pages(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  return (
    await Promise.all(
      entries.map((entry) => {
        const file = path.join(directory, entry.name);
        return entry.isDirectory()
          ? pages(file)
          : file.endsWith(".md")
            ? [file]
            : [];
      }),
    )
  ).flat();
}

const sourceMap = {};
for (const lang of ["zh", "en"]) {
  for (const file of await pages(path.join(docs, lang))) {
    const relative = posix(path.relative(docs, file));
    sourceMap[relative === `${lang}/index.md` ? `${lang}/docs.md` : relative] =
      posix(path.relative(root, file));
  }
  const suffix = lang === "zh" ? "_ZH" : "";
  sourceMap[`${lang}/getting-started/overview.md`] = `README${suffix}.md`;
  sourceMap[`${lang}/development/contributing.md`] = `CONTRIBUTING${suffix}.md`;
  sourceMap[`${lang}/plugins/alpha158.md`] = `plugins/a158/README${suffix}.md`;
  sourceMap[`${lang}/plugins/alpha158-enhanced.md`] =
    `plugins/a158_enhanced/README${suffix}.md`;
}
const routes = new Map(
  Object.entries(sourceMap).map(([route, original]) => [
    original,
    `/${route.replace(/\.md$/, "")}`,
  ]),
);
const assets = new Map();

await rm(output, { recursive: true, force: true });
await cp(docs, output, {
  recursive: true,
  filter: (file) => path.basename(file) !== ".DS_Store",
});
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
    if (source === "docs/README.md")
      return `/${route.slice(0, 2)}/docs${suffix}`;
    if (routes.has(source)) return `${routes.get(source)}${suffix}`;
    const kind = statSync(path.join(root, source)).isDirectory()
      ? "tree"
      : "blob";
    return `${repository}/${kind}/main/${source}${suffix}`;
  };
  const content = mapLinks(
    await readFile(path.join(root, original), "utf8"),
    (href, image, html) => {
      const url = resolve(href, image);
      return html && !image && url.startsWith("/")
        ? `${base}${url.slice(1)}`
        : url;
    },
  );
  await mkdir(path.dirname(path.join(output, route)), { recursive: true });
  await writeFile(path.join(output, route), content);
}
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
