<script setup lang="ts">
import { computed } from "vue";
import { useData, withBase } from "vitepress";
const { page, lang } = useData();
const zh = computed(() => lang.value.startsWith("zh"));
const markdown = computed(() => withBase(`/${page.value.relativePath}`));
</script>

<template>
  <nav
    class="doc-tools"
    :aria-label="zh ? '文档资源' : 'Documentation resources'"
  >
    <a :href="markdown" target="_blank" rel="noopener">
      <span class="doc-tool-icon" aria-hidden="true">MD</span>
      {{ zh ? "查看 Markdown" : "View Markdown" }}
      <span class="doc-tool-arrow" aria-hidden="true">↗</span>
    </a>
    <a :href="withBase('/llms.txt')" target="_blank" rel="noopener">
      <span class="doc-tool-icon" aria-hidden="true">AI</span>
      LLMs.txt <span class="doc-tool-arrow" aria-hidden="true">↗</span>
    </a>
  </nav>
</template>
