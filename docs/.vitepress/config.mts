import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitepress";
import { groups, groupRoutes } from "./navigation.mjs";
import { mapLinks } from "./links.mjs";

const source = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repository = "https://github.com/FlowLLM-AI/AxonX";
const base = process.env.DOCS_BASE || "/AxonX/";
const siteUrl = (
  process.env.DOCS_SITE_URL || "https://flowllm-ai.github.io"
).replace(/\/$/, "");
const sourceMap: Record<string, string> = JSON.parse(
  fs.readFileSync(path.join(source, ".source-map.json"), "utf8"),
);
const title = (file: string) =>
  fs.readFileSync(path.join(source, file), "utf8").match(/^#\s+(.+)$/m)?.[1] ||
  file;

function locale(lang: "zh" | "en") {
  const zh = lang === "zh";
  const link = (page: string) => `/${lang}/${page}`;
  const pages = (files: readonly string[]) =>
    files.map((file) => ({
      text: title(`${lang}/${file}.md`),
      link: link(file),
    }));
  const navigation = groups.map((group) => ({
    text: group.labels[zh ? 0 : 1],
    page: group.page,
    routes: groupRoutes(group).map(link),
    items: group.sections.map(([cn, en, files]) => ({
      text: zh ? cn : en,
      items: pages(files),
    })),
  }));
  return {
    label: zh ? "简体中文" : "English",
    lang: zh ? "zh-CN" : "en",
    description: zh
      ? "面向金融量化研究的 Agent Harness。"
      : "An agent-native harness for quantitative research.",
    themeConfig: {
      nav: [
        {
          text: zh ? "首页" : "Home",
          link: link(""),
          activeMatch: zh ? "^/zh/$" : "^(?:/en/|/)$",
        },
        ...navigation.map((group) => ({
          text: group.text,
          link: link(group.page),
          activeMatch: `^(?:${group.routes.join("|")})$`,
        })),
      ],
      sidebar: Object.fromEntries(
        navigation.flatMap((group) =>
          group.routes.map((route) => [route, group.items]),
        ),
      ),
      outline: {
        label: zh ? "本页目录" : "On this page",
        level: [2, 3] as [number, number],
      },
      docFooter: {
        prev: zh ? "上一篇" : "Previous",
        next: zh ? "下一篇" : "Next",
      },
      editLink: {
        pattern: `${repository}/edit/main/:path`,
        text: zh ? "在 GitHub 编辑此页" : "Edit this page on GitHub",
      },
      returnToTopLabel: zh ? "回到顶部" : "Back to top",
      sidebarMenuLabel: zh ? "目录" : "Menu",
    },
  };
}

export default defineConfig({
  title: "AxonX",
  description: "An agent-native harness for quantitative research.",
  base,
  outDir: path.resolve(source, "../../dist"),
  cleanUrls: true,
  lastUpdated: false,
  ignoreDeadLinks: [/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/],
  head: [
    [
      "link",
      { rel: "icon", type: "image/svg+xml", href: `${base}axonx-icon.svg` },
    ],
  ],
  locales: { zh: locale("zh"), en: locale("en") },
  themeConfig: {
    logo: "/axonx-icon.svg",
    siteTitle: "AxonX",
    nav: locale("en").themeConfig.nav,
    socialLinks: [{ icon: "github", link: repository }],
    search: {
      provider: "local",
      options: {
        locales: {
          zh: {
            translations: {
              button: { buttonText: "搜索文档", buttonAriaLabel: "搜索文档" },
              modal: {
                noResultsText: "没有找到结果",
                resetButtonTitle: "清除搜索",
                footer: {
                  selectText: "选择",
                  navigateText: "切换",
                  closeText: "关闭",
                },
              },
            },
          },
        },
      },
    },
    footer: {
      message: "Agent-native quant research.",
      copyright: "AxonX · FlowLLM-AI",
    },
  },
  transformPageData(page) {
    page.filePath = sourceMap[page.relativePath] || page.relativePath;
  },
  buildEnd(config) {
    // Static hosts may serve text without a charset; the BOM makes UTF-8 unambiguous.
    const writeText = (file: string, content: string) =>
      fs.writeFileSync(
        path.join(config.outDir, file),
        "\uFEFF" + content,
        "utf8",
      );
    const index = [
      "# AxonX",
      "",
      "> An agent-native harness for quantitative research.",
      "",
    ];
    const full = ["# AxonX Documentation", ""];
    for (const [page, original] of Object.entries(sourceMap)) {
      const content = mapLinks(
        fs.readFileSync(path.join(source, page), "utf8"),
        (href) => {
          if (/^(?:[a-z]+:|#)/i.test(href)) return href;
          if (href.startsWith(base)) return `${siteUrl}${href}`;
          const relative = href.startsWith("/")
            ? href.slice(1)
            : path.posix.normalize(
                path.posix.join(path.posix.dirname(page), href),
              );
          return `${siteUrl}${base}${relative}`;
        },
      );
      index.push(
        `- [${title(page)}](${siteUrl}${base}${page.replace(/\.md$/, "")})`,
      );
      full.push(`<!-- ${original} -->`, content, "\n---\n");
      const target = path.join(config.outDir, page);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      writeText(page, content);
    }
    writeText("llms.txt", index.join("\n"));
    writeText("llms-full.txt", full.join("\n"));
  },
});
