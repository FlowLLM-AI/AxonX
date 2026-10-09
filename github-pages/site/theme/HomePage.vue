<script setup lang="ts">
import { ref } from "vue";
import { withBase } from "vitepress";
import { useSiteI18n } from "./i18n";
import {
  stages,
  paths,
  journeys,
  screens,
  capabilities,
  updates,
} from "./home";

const { language, t, link, playground } = useSiteI18n();
const selected = ref(0);
const viewport = ref<HTMLElement>();
function selectScreen(index: number) {
  viewport.value?.scrollTo({ left: index * viewport.value.clientWidth });
}
function syncScreen() {
  const container = viewport.value;
  if (!container?.clientWidth) return;
  selected.value = Math.max(
    0,
    Math.min(
      screens.length - 1,
      Math.round(container.scrollLeft / container.clientWidth),
    ),
  );
}
function moveTab(event: KeyboardEvent, target: number) {
  const index = (target + screens.length) % screens.length;
  selectScreen(index);
  (event.currentTarget as HTMLElement).parentElement
    ?.querySelectorAll<HTMLButtonElement>("button")
    [index]?.focus({ preventScroll: true });
}
</script>

<template>
  <main class="axon-home">
    <p class="star-prompt section-lead shell">
      <a href="https://github.com/FlowLLM-AI/AxonX">
        {{ t.home.star }}
        ↗
      </a>
    </p>
    <section class="hero shell">
      <div class="hero-copy">
        <p class="eyebrow">
          <span class="status-dot" /> AGENT-NATIVE QUANT HARNESS
        </p>
        <h1>
          {{ t.home.headline }}<br /><span>{{ t.home.headlineAccent }}</span>
        </h1>
        <p class="hero-lead">
          {{ t.home.lead }}
        </p>
        <div class="actions">
          <a class="action secondary" :href="playground" target="_self">
            {{ t.home.tryStudio }} <span>→</span>
          </a>
          <a class="action primary" :href="link('getting-started/quickstart')"
            >{{ t.home.getStarted }} <span>→</span></a
          >
          <a class="action secondary" :href="link('research/workflow')"
            >{{ t.home.exploreWorkflow }} <span>↗</span></a
          >
        </div>
        <div class="hero-meta">
          <span>PLUGIN</span><i /> <span>JOB</span><i /><span>TASK</span
          ><i /><span>RESULT</span>
        </div>
      </div>
      <div class="workflow">
        <div class="workflow-heading">
          <img :src="withBase('/axonx-icon.svg')" alt="" />
          <div>
            <strong>{{ t.home.workflowTitle }}</strong
            ><small>AXONX / RESEARCH WORKSPACE</small>
          </div>
          <span class="workflow-mark">↗</span>
        </div>
        <div class="pipeline">
          <template v-for="(stage, index) in stages" :key="stage.id">
            <a class="stage" :class="stage.color" :href="link(stage.page)"
              ><span class="stage-number">{{ stage.number }}</span
              ><strong>{{ t.home.stages[stage.id] }}</strong
              ><span class="stage-arrow">↗</span></a
            >
            <div v-if="index === 1" class="branch">
              <span>↳</span
              ><a :href="link('research/results')"
                >{{ t.home.factorAnalysis }} ↗</a
              ><small>{{ t.home.etlBranch }}</small>
            </div>
          </template>
        </div>
        <div class="workflow-footer">
          <span class="status-dot" />
          {{ t.home.evidence }}<span>TRACEABLE BY DESIGN</span>
        </div>
      </div>
    </section>

    <section class="updates-section shell" aria-labelledby="latest-updates">
      <div class="section-heading">
        <h2 id="latest-updates">{{ t.home.updatesTitle }}</h2>
      </div>
      <ul class="updates-list">
        <li v-for="item in updates" :key="item.id">
          <strong>{{ t.home.updates[item.id].title }}</strong>
          <p>
            {{ t.home.updates[item.id].description }}
            <a
              :href="item.page ? link(item.page) : item.href || playground"
              :target="item.target"
            >
              {{ t.home.updates[item.id].label }} ↗
            </a>
          </p>
        </li>
      </ul>
    </section>

    <section class="paths shell" :aria-label="t.home.pathsLabel">
      <a
        v-for="item in paths"
        :key="item.id"
        class="path-card"
        :href="link(item.page)"
        ><p class="eyebrow">{{ item.label }}</p>
        <h2>{{ t.home.paths[item.id].title }}</h2>
        <p>{{ t.home.paths[item.id].description }}</p>
        <span class="card-arrow">↗</span></a
      >
    </section>

    <section class="studio-section">
      <div class="shell">
        <div class="section-heading">
          <div>
            <p class="eyebrow">01 / AXONX STUDIO</p>
            <h2>
              {{ t.home.showcaseTitle }}
            </h2>
          </div>
          <a class="text-link" :href="link('getting-started/studio')"
            >{{ t.home.exploreStudio }} ↗</a
          >
        </div>
        <p class="section-lead">
          {{ t.home.showcaseLead }}
        </p>
        <div
          class="screen-tabs"
          role="tablist"
          :aria-label="t.home.showcaseLabel"
        >
          <button
            v-for="(item, index) in screens"
            :id="`screen-tab-${index}`"
            :key="item.id"
            type="button"
            role="tab"
            :aria-selected="selected === index"
            :aria-controls="`studio-preview-${index}`"
            @click="selectScreen(index)"
            @keydown.right.prevent="moveTab($event, index + 1)"
            @keydown.left.prevent="moveTab($event, index - 1)"
            @keydown.home.prevent="moveTab($event, 0)"
            @keydown.end.prevent="moveTab($event, screens.length - 1)"
            :tabindex="selected === index ? 0 : -1"
          >
            {{ t.home.screens[item.id].title }}
          </button>
        </div>
        <div class="screen-carousel">
          <button
            class="screen-arrow screen-arrow-prev"
            type="button"
            :aria-label="t.home.previousSlide"
            :disabled="selected === 0"
            @click="selectScreen(selected - 1)"
          >
            <span aria-hidden="true">←</span>
          </button>
          <div
            ref="viewport"
            class="screen-viewport"
            @scroll.passive="syncScreen"
          >
            <div
              v-for="(item, index) in screens"
              :id="`studio-preview-${index}`"
              :key="item.id"
              class="screen-slide"
              role="tabpanel"
              :aria-labelledby="`screen-tab-${index}`"
              :inert="selected !== index"
            >
              <div class="screen-panel">
                <div class="screen-top">
                  <span class="window-dots">● ● ●</span>
                  <span>AXONX STUDIO / {{ item.label }}</span>
                  <span class="screen-live">{{ t.home.actualInterface }}</span>
                </div>
                <a :href="link(item.page)">
                  <img
                    :src="item.image"
                    :alt="t.home.screens[item.id].title"
                    loading="lazy"
                    :width="item.width"
                    :height="item.height"
                  />
                </a>
              </div>
              <div class="screen-caption">
                <p>{{ t.home.screens[item.id].description }}</p>
                <a class="text-link" :href="link(item.page)">
                  {{ t.home.readGuide }} ↗
                </a>
              </div>
            </div>
          </div>
          <button
            class="screen-arrow screen-arrow-next"
            type="button"
            :aria-label="t.home.nextSlide"
            :disabled="selected === screens.length - 1"
            @click="selectScreen(selected + 1)"
          >
            <span aria-hidden="true">→</span>
          </button>
        </div>
        <div class="screen-progress" aria-hidden="true">
          <span>{{ String(selected + 1).padStart(2, "0") }}</span>
          <div class="screen-progress-bars">
            <span
              v-for="(_, index) in screens"
              :key="index"
              :class="{ active: selected === index }"
            />
          </div>
          <span>{{ String(screens.length).padStart(2, "0") }}</span>
        </div>
      </div>
    </section>

    <section class="capability-section shell">
      <div class="section-heading">
        <div>
          <p class="eyebrow">02 / HARNESS CORE</p>
          <h2>
            {{ t.home.capabilitiesTitle }}
          </h2>
        </div>
      </div>
      <div class="capabilities">
        <a v-for="item in capabilities" :key="item.id" :href="link(item.page)"
          ><p class="eyebrow">{{ item.label }} <span>↗</span></p>
          <h3>{{ t.home.capabilities[item.id].title }}</h3>
          <p>{{ t.home.capabilities[item.id].description }}</p></a
        >
      </div>
    </section>

    <section class="capability-section shell">
      <div class="section-heading">
        <div>
          <p class="eyebrow">03 / CONTINUE YOUR RESEARCH</p>
          <h2>{{ t.home.journeysTitle }}</h2>
        </div>
        <a class="text-link" :href="link('docs')"
          >{{ t.home.documentationMap }} ↗</a
        >
      </div>
      <div class="capabilities">
        <a v-for="item in journeys" :key="item.id" :href="link(item.page)">
          <p class="eyebrow">{{ item.label }} <span>↗</span></p>
          <h3>{{ t.home.journeys[item.id].title }}</h3>
          <p>{{ t.home.journeys[item.id].description }}</p>
        </a>
      </div>
    </section>

    <section class="case-study shell">
      <div class="section-heading">
        <div>
          <p class="eyebrow">04 / AGENT RESEARCH CASE</p>
          <h2>
            {{ t.home.caseTitle }}
          </h2>
        </div>
        <a class="text-link" :href="link('research/experiments')"
          >{{ t.home.experimentDesign }} ↗</a
        >
      </div>
      <p class="section-lead">
        {{ t.home.caseDescription }}
      </p>
      <div class="actions">
        <a
          class="action secondary"
          :href="
            link('getting-started/overview') +
            (language === 'zh'
              ? '#benchmark-agent-开发市场横截面增强特征'
              : '#benchmark-agent-developed-market-cross-sectional-features')
          "
          >{{ t.home.benchmark }} ↗</a
        >
        <a class="text-link" :href="link('plugins/qlib-factor')"
          >{{ t.home.reproduction }} ↗</a
        >
      </div>
    </section>

    <section class="closing shell">
      <div>
        <p class="eyebrow">BUILD YOUR RESEARCH LOOP</p>
        <h2>{{ t.home.closingTitle }}</h2>
        <p>
          {{ t.home.closingDescription }}
        </p>
      </div>
      <div class="actions">
        <a class="action primary" :href="link('getting-started/quickstart')"
          >{{ t.home.runDemo }} →</a
        ><a class="action secondary" :href="link('docs')"
          >{{ t.home.browseDocs }} ↗</a
        >
      </div>
    </section>
  </main>
</template>
