import type { Theme } from "vitepress";
import DefaultTheme from "vitepress/theme";
import { h } from "vue";
import HomePage from "./HomePage.vue";
import DocTools from "./DocTools.vue";
import Preferences from "./Preferences.vue";
import ExperienceLink from "./ExperienceLink.vue";
import "./style.css";

export default {
  extends: DefaultTheme,
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      "doc-before": () => h(DocTools),
      "nav-bar-content-after": () => [h(ExperienceLink), h(Preferences)],
      "nav-screen-content-after": () => h(ExperienceLink),
    }),
  enhanceApp({ app }) {
    app.component("HomePage", HomePage);
  },
} satisfies Theme;
