<script setup lang="ts">
import { computed } from "vue";
import { withBase } from "vitepress";
import { useSiteI18n } from "./i18n";
import { stages } from "./home";
import readme from "./readme-home.json";

const { language, t, link, playground } = useSiteI18n();
const content = computed(() => readme[language.value]);
</script>

<template>
  <main class="axon-home">
    <p class="star-prompt section-lead shell">
      <a href="https://github.com/FlowLLM-AI/AxonX">{{ t.home.star }} ↗</a>
    </p>
    <section class="hero shell">
      <div class="hero-copy">
        <p class="eyebrow">
          <span class="status-dot" /> AGENT-NATIVE QUANT HARNESS
        </p>
        <h1>
          {{ t.home.headline }}<br /><span>{{ t.home.headlineAccent }}</span>
        </h1>
        <p class="hero-lead" v-html="content.summary" />
        <div class="actions">
          <a class="action primary" :href="link('agent/overview')"
            >{{ t.home.develop }} <span>→</span></a
          >
          <a class="action secondary" :href="link('getting-started/quickstart')"
            >{{ t.home.getStarted }} <span>→</span></a
          >
          <a class="action secondary" :href="playground" target="_self"
            >{{ t.home.tryStudio }} <span>↗</span></a
          >
        </div>
        <div class="hero-meta">
          <span>PROMPT</span><i /><span>PLUGIN</span><i /><span>TASK</span
          ><i /><span>EVIDENCE</span>
        </div>
      </div>
      <div class="workflow">
        <div class="workflow-heading">
          <img :src="withBase('/axonx-icon.svg')" alt="" />
          <div>
            <strong>{{ t.home.workflowTitle }}</strong
            ><small>AXONX / AGENT RESEARCH LOOP</small>
          </div>
          <span class="workflow-mark">↗</span>
        </div>
        <div class="pipeline">
          <a
            v-for="stage in stages"
            :key="stage.id"
            class="stage"
            :class="stage.color"
            :href="link(stage.page)"
          >
            <span class="stage-number">{{ stage.number }}</span
            ><strong>{{ t.home.stages[stage.id] }}</strong
            ><span class="stage-arrow">↗</span>
          </a>
        </div>
        <div class="workflow-footer">
          <span class="status-dot" />{{ t.home.evidence }}
        </div>
      </div>
    </section>
    <nav class="readme-jump-links shell" :aria-label="t.home.contents">
      <a
        v-for="section in content.sections.slice(0, 7)"
        :key="section.id"
        :href="`#${section.id}`"
        >{{ section.title }}</a
      >
    </nav>
    <section
      v-for="section in content.sections"
      :id="section.id"
      :key="`${language}-${section.id}`"
      class="readme-home-section shell"
    >
      <div class="vp-doc" v-html="section.html" />
    </section>
  </main>
</template>
