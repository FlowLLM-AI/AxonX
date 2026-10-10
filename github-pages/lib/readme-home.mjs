import { mapLinks } from "./links.mjs";

// Use Markdown tokens so headings inside code examples cannot split sections.
export function readmeSections(content, markdown) {
  const lines = content.split(/\r?\n/);
  const tokens = markdown.parse(content, {});
  const codeLines = new Set(
    tokens
      .filter((token) => ["fence", "code_block"].includes(token.type))
      .flatMap((token) =>
        Array.from(
          { length: token.map[1] - token.map[0] },
          (_, i) => token.map[0] + i,
        ),
      ),
  );
  const anchorLines = new Set(
    lines.flatMap((line, index) =>
      !codeLines.has(index) && /^<a\s+id="[^"]+"><\/a>\s*$/.test(line)
        ? [index]
        : [],
    ),
  );
  const headings = tokens.filter(
    (token) => token.type === "heading_open" && token.tag === "h2",
  );
  if (!headings.length) throw new Error("README homepage requires H2 sections");
  return headings.map((heading, index) => {
    const start = heading.map[0];
    const end = headings[index + 1]?.map[0] ?? lines.length;
    return {
      id: `readme-section-${index}`,
      title: lines[start].replace(/^\s*##\s+/, "").trim(),
      markdown: lines
        .slice(start, end)
        .filter((_, i) => !anchorLines.has(start + i))
        .join("\n")
        .trim(),
    };
  });
}

export function renderReadmeHome(content, markdown, { base, overview }) {
  const resolved = mapLinks(content, (href) => {
    if (href.startsWith("#")) return `${base}${overview}${href}`;
    if (href.startsWith(base) || !href.startsWith("/")) return href;
    return `${base}${href.slice(1)}`;
  });
  const section = readmeSections(resolved, markdown).find((section) =>
    ["Latest Updates", "最新更新"].includes(section.title),
  );
  if (!section) throw new Error("README homepage requires Latest Updates");
  const body = section.markdown.split("\n").slice(1).join("\n").trim();
  if (!body) throw new Error("README Latest Updates must not be empty");
  const list = markdown
    .parse(body, {})
    .find((token) => token.type === "bullet_list_open");
  if (!list) throw new Error("README Latest Updates requires an update list");
  const updates = body
    .split("\n")
    .slice(...list.map)
    .join("\n");
  return { title: section.title, html: markdown.render(updates, {}) };
}
