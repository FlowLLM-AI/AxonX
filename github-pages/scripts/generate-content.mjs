import { cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const docs = path.join(root, "docs");
const output = path.join(root, "github-pages/.generated/site");
const repository = "https://github.com/FlowLLM-AI/AxonX";

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
const sourceMap = {};
for (const lang of ["zh", "en"]) {
  for (const file of await pages(path.join(docs, lang))) {
    const relative = path.relative(docs, file).split(path.sep).join("/");
    const target =
      relative === `${lang}/index.md` ? `${lang}/docs.md` : relative;
    const content = (await readFile(file, "utf8")).replace(
      /(!?\[[^\]\n]*\]\()([^\s)]+)([^)]*\))/g,
      (match, start, href, end) => {
        if (/^(?:[a-z]+:|\/|#)/i.test(href)) return match;
        const [pathname, suffix = ""] = href.split(/(?=[?#])/);
        const resolved = path.resolve(path.dirname(file), pathname);
        const local = path.relative(docs, resolved).split(path.sep).join("/");
        if (local.startsWith("../")) {
          const source = path
            .relative(root, resolved)
            .split(path.sep)
            .join("/");
          return `${start}${repository}/${
            path.extname(resolved) ? "blob" : "tree"
          }/main/${source}${suffix}${end}`;
        }
        if (/^(zh|en)\/index\.md$/.test(local)) {
          return `${start}/${local.replace("index.md", "docs")}${suffix}${end}`;
        }
        return match;
      },
    );
    await writeFile(path.join(output, target), content);
    sourceMap[target] = `docs/${relative}`;
  }
  await writeFile(
    path.join(output, lang, "index.md"),
    `---\nlayout: page\nsidebar: false\ntitle: AxonX\n---\n\n<HomePage />\n`,
  );
}
await writeFile(
  path.join(output, "index.md"),
  "---\nlayout: page\nsidebar: false\ntitle: AxonX\n---\n\n<HomePage />\n",
);
await rm(path.join(output, "README.md"), { force: true });
await writeFile(
  path.join(output, ".source-map.json"),
  JSON.stringify(sourceMap, null, 2),
);
console.log(`Prepared ${Object.keys(sourceMap).length} documentation pages.`);
