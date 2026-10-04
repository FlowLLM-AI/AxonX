<script setup lang="ts">
import { computed } from "vue";
import { useData, withBase } from "vitepress";
import { useSiteI18n } from "./i18n";
const { page } = useData();
const { t } = useSiteI18n();
const markdown = computed(() => withBase(`/${page.value.relativePath}`));
</script>

<template>
  <nav class="doc-tools" :aria-label="t.docs.resources">
    <a :href="markdown" target="_blank" rel="noopener">
      <span class="doc-tool-icon" aria-hidden="true">MD</span>
      {{ t.docs.viewMarkdown }}
      <span class="doc-tool-arrow" aria-hidden="true">↗</span>
    </a>
    <a :href="withBase('/llms.txt')" target="_blank" rel="noopener">
      <span class="doc-tool-icon" aria-hidden="true">AI</span>
      LLMs.txt <span class="doc-tool-arrow" aria-hidden="true">↗</span>
    </a>
  </nav>
</template>
