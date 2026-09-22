import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import zh from "./locales/zh.json";

const supportedLanguages = ["en", "zh"] as const;
type AppLanguage = (typeof supportedLanguages)[number];

function initialLanguage(): AppLanguage {
  const saved =
    typeof localStorage === "undefined"
      ? null
      : localStorage.getItem("language");
  if (saved === "en" || saved === "zh") return saved;
  return typeof navigator !== "undefined" &&
    navigator.language.toLowerCase().startsWith("zh")
    ? "zh"
    : "en";
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    zh: { translation: zh },
  },
  lng: initialLanguage(),
  fallbackLng: "en",
  supportedLngs: supportedLanguages,
  nonExplicitSupportedLngs: true,
  interpolation: { escapeValue: false },
  returnNull: false,
});

export async function changeLanguage(language: AppLanguage) {
  await i18n.changeLanguage(language);
  if (typeof localStorage !== "undefined")
    localStorage.setItem("language", language);
  if (typeof document !== "undefined")
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
}

export function resolvedLocale() {
  return i18n.resolvedLanguage === "zh" ? "zh-CN" : "en-US";
}

if (typeof document !== "undefined")
  document.documentElement.lang = initialLanguage() === "zh" ? "zh-CN" : "en";

export default i18n;
