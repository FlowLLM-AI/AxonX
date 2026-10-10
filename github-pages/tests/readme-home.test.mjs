import assert from "node:assert/strict";
import { test } from "node:test";
import { createMarkdownRenderer } from "vitepress";
import { readmeSections, renderReadmeHome } from "../lib/readme-home.mjs";

const markdown = await createMarkdownRenderer(process.cwd(), { html: true });

test("homepage reads whole README sections and ignores headings in code examples", () => {
  const source =
    '# Project\n\n## What is AxonX?\n\nA research Harness.\n\n```md\n## Example only\n<a id="code-example"></a>\n```\n\n<a id="updates"></a>\n\n## Latest Updates\n\n- First update\n- New update\n';
  const sections = readmeSections(source, markdown);
  assert.equal(sections.length, 2);
  assert.equal(sections[1].title, "Latest Updates");
  assert.match(sections[0].markdown, /## Example only/);
  assert.match(sections[0].markdown, /id="code-example"/);
  assert.doesNotMatch(sections[0].markdown, /id="updates"/);
  assert.match(sections[1].markdown, /New update/);
});

test("homepage preserves README content, Unicode, mounted links and Playground transport", () => {
  for (const base of ["/", "/AxonX/"]) {
    const source = `## 最新更新\n\n**研究 Harness。**\n\n- [插件](/zh/plugins/qlib-factor) [开发](#agent)\n- <a href="${base}playground/?lang=zh" target="_self">试玩</a>\n\n![图片](/media/overview.svg)\n`;
    const result = renderReadmeHome(source, markdown, {
      base,
      overview: "zh/getting-started/overview",
    });
    assert.match(result.summary, /研究 Harness/);
    const html = result.sections[0].html;
    assert.ok(html.includes(`href="${base}zh/plugins/qlib-factor.html"`));
    assert.ok(
      html.includes(`href="${base}zh/getting-started/overview.html#agent"`),
    );
    assert.ok(
      html.includes(`href="${base}playground/?lang=zh" target="_self"`),
    );
    assert.ok(html.includes(`src="${base}media/overview.svg"`));
  }
});

test("missing README structure fails generation instead of publishing an empty homepage", () => {
  assert.throws(() => readmeSections("No sections", markdown), /H2 sections/);
  assert.throws(
    () =>
      renderReadmeHome("## Overview\n", markdown, {
        base: "/",
        overview: "en/overview",
      }),
    /introductory paragraph/,
  );
});
