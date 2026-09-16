import { useEffect, useState } from "react";
import type { Language, ThemePreference } from "../../types";

export function useAppPreferences() {
  const [language, setLanguage] = useState<Language>(() =>
    localStorage.getItem("axonx-language") === "en" ? "en" : "zh",
  );
  const [theme, setTheme] = useState<ThemePreference>(() => {
    const saved = localStorage.getItem("axonx-theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  });

  useEffect(() => {
    localStorage.setItem("axonx-language", language);
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    document.title = "AxonX Studio";
  }, [language]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        theme === "dark" || (theme === "system" && media.matches)
          ? "dark"
          : "light";
    };

    localStorage.setItem("axonx-theme", theme);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);

  return { language, setLanguage, theme, setTheme };
}
