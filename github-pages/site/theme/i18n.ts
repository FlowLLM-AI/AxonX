import { computed } from "vue";
import { useData, withBase } from "vitepress";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

const resources = { en, zh };

export function useSiteI18n() {
  const { lang } = useData();
  const language = computed(() => (lang.value.startsWith("zh") ? "zh" : "en"));
  return {
    language,
    t: computed(() => resources[language.value]),
    link: (page: string) => withBase(`/${language.value}/${page}`),
    playground: computed(() => withBase(`/playground/?lang=${language.value}`)),
  };
}
