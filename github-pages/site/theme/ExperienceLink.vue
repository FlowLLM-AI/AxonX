<script setup lang="ts">
import { useSiteI18n } from "./i18n";
const { t, playground } = useSiteI18n();
</script>

<template>
  <a class="experience-link" :href="playground" target="_self">
    {{ t.site.tryOnline }} <span aria-hidden="true">↗</span>
  </a>
</template>
