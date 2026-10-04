<script setup lang="ts">
import { useStorage } from "@vueuse/core";
import { computed, onMounted, watch } from "vue";
import { useData, useRouter, withBase } from "vitepress";

const { lang, page, isDark } = useData();
const router = useRouter();
const zh = computed(() => lang.value.startsWith("zh"));
const t = (cn: string, en: string) => (zh.value ? cn : en);
const language = useStorage("axonx-language", "");
const appearance = useStorage("vitepress-theme-appearance", "light");
const languageLabel = computed(() => t("切换到英文", "Switch to Chinese"));
const appearanceLabel = computed(() =>
  isDark.value
    ? t("切换到浅色主题", "Switch to light theme")
    : t("切换到深色主题", "Switch to dark theme"),
);

function applyLanguage() {
  if (language.value !== "en" && language.value !== "zh") return;
  if (lang.value.startsWith(language.value)) return;
  const path = page.value.relativePath
    .replace(/^(zh|en)\//, "")
    .replace(/(^|\/)index\.md$/, "$1")
    .replace(/\.md$/, "");
  router.go(
    withBase(`/${language.value}/${path}`) + location.search + location.hash,
  );
}

onMounted(() => {
  if (language.value !== "en" && language.value !== "zh") language.value = "";
  applyLanguage();
  watch(language, applyLanguage);
});
</script>

<template>
  <div class="site-preferences">
    <button
      type="button"
      class="preference-toggle"
      :aria-label="languageLabel"
      :title="languageLabel"
      @click="language = zh ? 'en' : 'zh'"
    >
      {{ zh ? "中" : "EN" }}
    </button>
    <button
      type="button"
      class="preference-toggle"
      :aria-label="appearanceLabel"
      :title="appearanceLabel"
      @click="appearance = isDark ? 'light' : 'dark'"
    >
      <span :class="isDark ? 'vpi-moon' : 'vpi-sun'" aria-hidden="true" />
    </button>
  </div>
</template>
