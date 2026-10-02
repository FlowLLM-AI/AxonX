import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitepress";
import { sections } from "./navigation";

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
  const section = (directory: string, omit: string[] = []) => {
    const [, cn, en, files] = sections.find(([name]) => name === directory)!;
    return {
      text: zh ? cn : en,
      items: pages(
        files
          .filter((file) => !omit.includes(file))
          .map((file) => `${directory}/${file}`),
      ),
    };
  };
  const groups = [
    {
      text: zh ? "文档" : "Docs",
      page: "docs",
      items: [
        { text: zh ? "文档导航" : "Documentation", items: pages(["docs"]) },
        section("getting-started", ["studio"]),
        section("concepts"),
        {
          text: zh ? "日常操作" : "Task operations",
          items: pages([
            "guides/task-management",
            "guides/workspace-files",
            "guides/plugin-management",
            "guides/remote-machines",
            "guides/task-sync",
            "guides/scheduling",
          ]),
        },
        {
          text: zh ? "部署与运维" : "Deployment & operations",
          items: pages([
            "guides/authentication",
            "guides/deployment",
            "guides/http-proxy",
            "guides/operations",
          ]),
        },
        {
          text: zh ? "CLI 与配置" : "CLI & configuration",
          items: pages([
            "reference/cli",
            "reference/client-configuration",
            "reference/configuration",
          ]),
        },
        { text: zh ? "常见问题" : "FAQ", items: pages(["faq"]) },
      ],
    },
    {
      text: zh ? "量化研究" : "Research",
      page: "research/workflow",
      items: [section("research")],
    },
    {
      text: "Studio",
      page: "getting-started/studio",
      items: [
        {
          text: "Studio",
          items: pages(["getting-started/studio", "development/studio"]),
        },
      ],
    },
    {
      text: "Agent",
      page: "agent/configuration",
      items: [
        section("agent"),
        { text: "Agent API", items: pages(["api/agent"]) },
      ],
    },
    {
      text: zh ? "开发者" : "Developers",
      page: "development/framework-extensions",
      items: [
        {
          text: zh ? "开发指南" : "Development guide",
          items: pages(["dev_guide"]),
        },
        section("development", ["studio"]),
        section("api", ["agent"]),
        {
          text: zh ? "Python 与扩展协议" : "Python & extension contracts",
          items: pages([
            "reference/python",
            "reference/task-contracts",
            "reference/plugin-manifest",
            "reference/research-artifacts",
          ]),
        },
      ],
    },
  ];
  const routes = (group: (typeof groups)[number]) =>
    group.items.flatMap(({ items }) => items.map(({ link }) => link));
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
        ...groups.map((group) => ({
          text: group.text,
          link: link(group.page),
          activeMatch: `^(?:${routes(group).join("|")})$`,
        })),
      ],
      sidebar: Object.fromEntries(
        groups.flatMap((group) =>
          routes(group).map((route) => [route, group.items]),
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
        pattern: `${repository}/edit/main/docs/:path`,
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
    page.filePath = (
      sourceMap[page.relativePath] || `docs/${page.relativePath}`
    ).replace(/^docs\//, "");
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
      const content = fs
        .readFileSync(path.join(source, page), "utf8")
        .replace(
          /(!?\[[^\]\n]*\]\()([^\s)]+)([^)]*\))/g,
          (match, start, href, end) => {
            if (/^(?:[a-z]+:|#)/i.test(href)) return match;
            const relative = href.startsWith("/")
              ? href.slice(1)
              : path.posix.normalize(
                  path.posix.join(path.posix.dirname(page), href),
                );
            const url = start.startsWith("!")
              ? `https://raw.githubusercontent.com/FlowLLM-AI/AxonX/main/docs/${relative}`
              : `${siteUrl}${base}${relative}`;
            return `${start}${url}${end}`;
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
