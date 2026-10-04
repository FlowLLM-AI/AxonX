import fs from "node:fs";
import path from "node:path";
import { documentTitle } from "./headings.mjs";
import { mapLinks } from "./links.mjs";

// Human and agent exports follow the same language, section, and page order.
export function writeExports({
  source,
  output,
  sourceMap,
  groups,
  base,
  siteUrl,
}) {
  const writeText = (file, content) => {
    const target = path.join(output, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, "\uFEFF" + content, "utf8");
  };
  const index = [
    "# AxonX",
    "",
    "> An agent-native harness for quantitative research.",
    "",
  ];
  const full = ["# AxonX Documentation", ""];
  for (const [lang, language] of [
    ["en", "English"],
    ["zh", "简体中文"],
  ]) {
    index.push(`## ${language}`, "");
    full.push(`## ${language}`, "");
    for (const group of groups) {
      const label = group.labels[lang === "zh" ? 0 : 1];
      index.push(`### ${label}`, "");
      full.push(`### ${label}`, "");
      for (const [, , pages] of group.sections) {
        for (const route of pages) {
          const page = `${lang}/${route}.md`;
          const original = sourceMap[page];
          const raw = fs.readFileSync(path.join(source, page), "utf8");
          const title = documentTitle(raw);
          const content = mapLinks(raw, (href) => {
            if (/^(?:[a-z]+:|#)/i.test(href)) return href;
            if (href.startsWith(base)) return `${siteUrl}${href}`;
            const relative = href.startsWith("/")
              ? href.slice(1)
              : path.posix.normalize(
                  path.posix.join(path.posix.dirname(page), href),
                );
            return `${siteUrl}${base}${relative}`;
          });
          index.push(`- [${title}](${siteUrl}${base}${lang}/${route})`);
          full.push(`<!-- ${original} -->`, content, "\n---\n");
          writeText(page, content);
        }
      }
      index.push("");
    }
  }
  writeText("llms.txt", index.join("\n"));
  writeText("llms-full.txt", full.join("\n"));
}
