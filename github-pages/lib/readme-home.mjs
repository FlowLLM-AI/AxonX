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
  const sections = readmeSections(resolved, markdown).map((section) => ({
    id: section.id,
    title: section.title,
    html: markdown.render(section.markdown, {}),
  }));
  const summary = sections[0].html.match(/<p>([\s\S]*?)<\/p>/)?.[1];
  if (!summary)
    throw new Error("README homepage requires an introductory paragraph");
  return { summary, sections };
}
