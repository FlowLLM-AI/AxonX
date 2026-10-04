<script setup lang="ts">
import { useEventListener, useStorage } from "@vueuse/core";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useData, useRouter, withBase } from "vitepress";

const { lang, page, isDark } = useData();
const router = useRouter();
const zh = computed(() => lang.value.startsWith("zh"));
const t = (cn: string, en: string) => (zh.value ? cn : en);
const language = useStorage("axonx-language", "");
// Share VitePress's preference: its appearance controller tracks system changes.
const appearance = useStorage("vitepress-theme-appearance", "auto");
const root = ref<HTMLElement>();
const open = ref<string | null>(null);
const close = () => (open.value = null);
watch(() => page.value.relativePath, close);
const menus = computed(() => [
  {
    id: "language",
    title: t("语言", "Language"),
    icon: "vpi-languages",
    selected: language.value || (zh.value ? "zh" : "en"),
    options: [
      ["browser", t("跟随浏览器", "Follow browser")],
      ["zh", "简体中文"],
      ["en", "English"],
    ],
  },
  {
    id: "appearance",
    title: t("明暗模式", "Appearance"),
    icon: isDark.value ? "vpi-moon" : "vpi-sun",
    selected: appearance.value,
    options: [
      ["auto", t("跟随系统", "Follow system")],
      ["light", t("亮色", "Light")],
      ["dark", t("暗色", "Dark")],
    ],
  },
]);
function select(menu: string, value: string) {
  (menu === "language" ? language : appearance).value = value;
  open.value = null;
}

function applyLanguage() {
  if (!["en", "zh", "browser"].includes(language.value)) return;
  const browser =
    navigator.languages.find((value) => /^(zh|en)(-|$)/i.test(value)) || "en";
  const target =
    language.value === "browser"
      ? browser.toLowerCase().startsWith("zh")
        ? "zh"
        : "en"
      : language.value;
  if (lang.value.startsWith(target)) return;
  const path = page.value.relativePath
    .replace(/^(zh|en)\//, "")
    .replace(/(^|\/)index\.md$/, "$1")
    .replace(/\.md$/, "");
  router.go(withBase(`/${target}/${path}`) + location.search + location.hash);
}

onMounted(() => {
  const closeOutside = (event: Event) => {
    if (!event.composedPath().includes(root.value!)) close();
  };
  useEventListener(window, "pointerdown", closeOutside, { capture: true });
  useEventListener(window, "focusin", closeOutside);
  useEventListener(window, "keydown", (event) => {
    if (event.key === "Escape") close();
  });
  applyLanguage();
  watch(language, applyLanguage);
  window.addEventListener("languagechange", followBrowser);
});
onUnmounted(() => window.removeEventListener("languagechange", followBrowser));
function followBrowser() {
  if (language.value === "browser") applyLanguage();
}
</script>

<template>
  <div ref="root" class="site-preferences">
    <div v-for="menu in menus" :key="menu.id" class="preference-menu">
      <button
        type="button"
        class="preference-trigger"
        :aria-label="menu.title"
        :aria-expanded="open === menu.id"
        :aria-controls="`preference-${menu.id}`"
        @click="open = open === menu.id ? null : menu.id"
      >
        <span :class="menu.icon" /><span class="vpi-chevron-down" />
      </button>
      <fieldset
        v-if="open === menu.id"
        :id="`preference-${menu.id}`"
        class="preference-options"
      >
        <legend class="visually-hidden">{{ menu.title }}</legend>
        <label v-for="[value, label] in menu.options" :key="value">
          <input
            type="radio"
            :name="`site-${menu.id}`"
            :value="value"
            :checked="menu.selected === value"
            @click="select(menu.id, value)"
            @change="select(menu.id, value)"
          />
          <span>{{ label }}</span
          ><span class="preference-check" aria-hidden="true">✓</span>
        </label>
      </fieldset>
    </div>
  </div>
</template>
