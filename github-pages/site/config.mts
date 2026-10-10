import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitepress";
import { groups, groupRoutes } from "../../docs/.vitepress/navigation.mjs";
import { repository } from "../lib/site-model.mjs";
import { documentTitle } from "../lib/headings.mjs";
import { siteSettings } from "../lib/settings.mjs";
import { writeExports } from "../lib/exports.mjs";
import en from "./theme/locales/en.json";
import zh from "./theme/locales/zh.json";

const resources = { en, zh };

const source = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../.generated/site",
);
const { base, siteUrl } = siteSettings();
const sourceMap: Record<string, string> = JSON.parse(
  fs.readFileSync(path.join(source, ".source-map.json"), "utf8"),
);
const title = (file: string) =>
  documentTitle(fs.readFileSync(path.join(source, file), "utf8")) || file;

function locale(lang: "zh" | "en") {
  const t = resources[lang].site;
  const link = (page: string) => `/${lang}/${page}`;
  const pages = (files: readonly string[]) =>
    files.map((file) => ({
      text: title(`${lang}/${file}.md`),
      link: link(file),
    }));
  const navigation = groups.map((group) => ({
    text: group.labels[lang === "zh" ? 0 : 1],
    page: group.page,
    routes: groupRoutes(group).map(link),
    items: group.sections.map(([cn, en, files]) => ({
      text: lang === "zh" ? cn : en,
      items: pages(files),
    })),
  }));
  return {
    label: t.label,
    lang: t.lang,
    description: t.description,
    themeConfig: {
      nav: [
        {
          text: t.home,
          link: link(""),
          activeMatch: lang === "zh" ? "^/zh/$" : "^(?:/en/|/)$",
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
        label: t.outline,
        level: [2, 3] as [number, number],
      },
      docFooter: {
        prev: t.prev,
        next: t.next,
      },
      editLink: {
        pattern: `${repository}/edit/main/:path`,
        text: t.edit,
      },
      returnToTopLabel: t.returnToTop,
      sidebarMenuLabel: t.menu,
    },
  };
}

export default defineConfig({
  title: "AxonX",
  lang: "en",
  description: en.site.description,
  base,
  outDir: path.resolve(source, "../../dist"),
  cleanUrls: true,
  lastUpdated: false,
  ignoreDeadLinks: [/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/],
  head: [
    [
      "script",
      { id: "axonx-theme-default" },
      `(() => {
        const theme = localStorage.getItem("vitepress-theme-appearance");
        if (theme !== "light" && theme !== "dark")
          localStorage.setItem("vitepress-theme-appearance", "light");
      })();`,
    ],
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
        locales: Object.fromEntries(
          Object.entries(resources).map(([lang, resource]) => [
            lang,
            { translations: resource.search },
          ]),
        ),
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
    writeExports({
      source,
      output: config.outDir,
      sourceMap,
      groups,
      base,
      siteUrl,
    });
  },
});
