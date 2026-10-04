<script setup lang="ts">
import { useStorage } from "@vueuse/core";
import { computed, onMounted, onUnmounted } from "vue";
import { useData, useRouter, withBase } from "vitepress";
import { useSiteI18n } from "./i18n";
import { initialLanguage, languageRoute } from "./language.mjs";

const { page, isDark } = useData();
const { language, t } = useSiteI18n();
const router = useRouter();
const saved = useStorage("language", "");
const appearance = useStorage("vitepress-theme-appearance", "light");
const appearanceLabel = computed(() =>
  isDark.value ? t.value.preferences.light : t.value.preferences.dark,
);

function navigate(next: "en" | "zh", replace = false) {
  const href = withBase(
    languageRoute(
      page.value.isNotFound ? "index.md" : page.value.relativePath,
      next,
      location.search,
      location.hash,
    ),
  );
  if (replace) history.replaceState(history.state, "", href);
  return router.go(href);
}

function toggleLanguage() {
  const next = language.value === "zh" ? "en" : "zh";
  saved.value = next;
  void navigate(next);
}

function applyLanguage() {
  if (page.value.isNotFound) return;
  const next = initialLanguage({
    relativePath: page.value.relativePath,
    search: location.search,
    saved: saved.value,
    browser: navigator.language,
  });
  if (next !== language.value || page.value.relativePath === "index.md")
    return navigate(next, true);
}

const previousRouteChange = router.onAfterRouteChange;
async function onRouteChange(href: string) {
  await previousRouteChange?.(href);
  await applyLanguage();
}

onMounted(() => {
  router.onAfterRouteChange = onRouteChange;
  void applyLanguage();
});
onUnmounted(() => {
  if (router.onAfterRouteChange === onRouteChange)
    router.onAfterRouteChange = previousRouteChange;
});
</script>

<template>
  <div class="site-preferences">
    <button
      type="button"
      class="preference-toggle"
      :aria-label="t.preferences.language"
      :title="t.preferences.language"
      @click="toggleLanguage"
    >
      {{ language === "zh" ? "中" : "EN" }}
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
