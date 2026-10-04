<script setup lang="ts">
import { computed, ref } from "vue";
import { useData, withBase } from "vitepress";
import lineage from "../../figures/studio/task-lineage.png";
import training from "../../figures/studio/training-curves.png";
import backtest from "../../figures/studio/backtest-overall.png";
import comparison from "../../figures/studio/strategy-overview.png";

const { lang } = useData();
const zh = computed(() => lang.value.startsWith("zh"));
const t = (cn: string, en: string) => (zh.value ? cn : en);
const link = (page: string) => withBase(`/${zh.value ? "zh" : "en"}/${page}`);
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
const stages = [
  ["01", "市场数据", "Market data", "research/tushare", "cyan"],
  ["02", "ETL 特征", "ETL features", "research/workflow", "violet"],
  ["03", "模型训练", "Model training", "research/results", "blue"],
  ["04", "离线预测", "Prediction", "research/results", "amber"],
  ["05", "策略回测", "Backtesting", "research/backtest", "green"],
];
const paths = [
  [
    "01 / GET STARTED",
    "运行第一个任务",
    "Run your first task",
    "用内置 demo，完成提交、等待与结果检查。",
    "Submit, follow, and inspect a built-in demo task.",
    "getting-started/quickstart",
  ],
  [
    "02 / RESEARCH",
    "开展量化研究",
    "Build a research workflow",
    "连接数据、特征、训练、预测和回测产物。",
    "Connect data, features, training, predictions, and backtests.",
    "research/overview",
  ],
  [
    "03 / AGENT",
    "接入研究 Agent",
    "Connect your agent",
    "选择外部 Skill / CLI / MCP，或 Studio 内置会话。",
    "Choose an external Skill / CLI / MCP integration or built-in Studio sessions.",
    "agent/overview",
  ],
];
const journeys = [
  [
    "AGENT",
    "让 Agent 操作研究",
    "Research with an agent",
    "从发现契约到执行、等待和检查产物。",
    "Discover contracts, execute, wait, and inspect artifacts.",
    "agent/external",
  ],
  [
    "EXPERIMENT",
    "设计可检查的实验",
    "Design inspectable experiments",
    "固定控制变量，筛选方案，再做独立确认。",
    "Fix controls, screen candidates, then confirm independently.",
    "research/experiments",
  ],
  [
    "OPERATIONS",
    "管理执行环境",
    "Manage execution environments",
    "连接远程机器，维护任务、文件和服务。",
    "Connect remote machines and maintain tasks, files, and services.",
    "guides/remote-machines",
  ],
  [
    "DEVELOP",
    "扩展研究能力",
    "Extend research capabilities",
    "编写插件，复用 Task 契约与框架扩展点。",
    "Build plugins using Task contracts and framework extension points.",
    "dev_guide",
  ],
];
const screens = [
  [
    "任务血缘",
    "Task lineage",
    lineage,
    "concepts/task-lineage",
    "检查运行记录，追踪上游产物。",
    "Inspect execution records and trace upstream artifacts.",
    796,
    442,
  ],
  [
    "模型训练",
    "Model training",
    training,
    "research/results",
    "从训练配置到验证曲线，检查模型证据。",
    "Inspect the evidence, from configuration to validation curves.",
    1190,
    532,
  ],
  [
    "策略回测",
    "Backtesting",
    backtest,
    "research/backtest",
    "把收益、成本与质量放在一起解读。",
    "Read returns, costs, and quality together.",
    1190,
    388,
  ],
  [
    "策略比较",
    "Strategy comparison",
    comparison,
    "research/strategy-comparison",
    "在共同区间内，理解策略之间的差异。",
    "Understand strategy differences over a shared period.",
    1168,
    630,
  ],
] as const;
const capabilities = [
  [
    "PLUGIN",
    "研究能力，独立扩展",
    "Research, independently extensible",
    "将算法和任务打包为插件，保留清晰的输入输出契约。",
    "Package algorithms and tasks as plugins with explicit input and output contracts.",
    "plugins/management",
  ],
  [
    "TASK",
    "运行过程，完整记录",
    "A record of every run",
    "状态、日志、参数和产物，汇聚到同一个任务工作区。",
    "Keep status, logs, parameters, and artifacts in one task workspace.",
    "concepts/task-lifecycle",
  ],
  [
    "MACHINE",
    "多台机器，统一入口",
    "Multiple machines, one entry point",
    "通过统一接口查看远程任务、机器资源与研究结果。",
    "Access remote tasks, machine resources, and research results through a shared interface.",
    "guides/remote-machines",
  ],
  [
    "JOB API",
    "Studio、CLI 与 Agent 协同",
    "Studio, CLI, and agents connected",
    "共享 Job 接口与工作区记录，围绕研究证据持续迭代。",
    "Share Job interfaces and workspace records to iterate on research evidence.",
    "api/overview",
  ],
];
</script>

<template>
  <main class="axon-home">
    <section class="hero shell">
      <div class="hero-copy">
        <p class="eyebrow">
          <span class="status-dot" /> AGENT-NATIVE QUANT HARNESS
        </p>
        <h1>
          {{ t("金融量化研究", "Financial quant research.") }}<br /><span>{{
            t("可追踪的闭环。", "Connected. Traceable.")
          }}</span>
        </h1>
        <p class="hero-lead">
          {{
            t(
              "面向金融量化研究的 Agent Harness。用插件组织算法，用 Task 保存运行证据，让 Studio、CLI / MCP 与 Agent 协同工作。",
              "An agent-native harness for financial quantitative research. Organize algorithms as plugins, preserve evidence as Tasks, and connect Studio, CLI / MCP, and agents.",
            )
          }}
        </p>
        <div class="actions">
          <a
            class="action secondary"
            :href="withBase(`/playground/?lang=${zh ? 'zh' : 'en'}`)"
            target="_self"
          >
            {{ t("体验 Studio", "Try Studio") }} <span>→</span>
          </a>
          <a class="action primary" :href="link('getting-started/quickstart')"
            >{{ t("快速开始", "Get started") }} <span>→</span></a
          >
          <a class="action secondary" :href="link('research/workflow')"
            >{{ t("查看研究流程", "Explore the workflow") }} <span>↗</span></a
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
            <strong>{{ t("从数据到研究证据", "From data to evidence") }}</strong
            ><small>AXONX / RESEARCH WORKSPACE</small>
          </div>
          <span class="workflow-mark">↗</span>
        </div>
        <div class="pipeline">
          <template v-for="(stage, index) in stages" :key="stage[0]">
            <a class="stage" :class="stage[4]" :href="link(stage[3])"
              ><span class="stage-number">{{ stage[0] }}</span
              ><strong>{{ t(stage[1], stage[2]) }}</strong
              ><span class="stage-arrow">↗</span></a
            >
            <div v-if="index === 1" class="branch">
              <span>↳</span
              ><a :href="link('research/results')"
                >{{ t("因子分析", "Factor analysis") }} ↗</a
              ><small>{{
                t("ETL 的独立分支", "Independent ETL branch")
              }}</small>
            </div>
          </template>
        </div>
        <div class="workflow-footer">
          <span class="status-dot" />
          {{
            t(
              "参数 · 日志 · 血缘 · 产物",
              "Parameters · Logs · Lineage · Artifacts",
            )
          }}<span>TRACEABLE BY DESIGN</span>
        </div>
      </div>
    </section>

    <section
      class="paths shell"
      :aria-label="t('选择开始路径', 'Choose your starting point')"
    >
      <a
        v-for="item in paths"
        :key="item[0]"
        class="path-card"
        :href="link(item[5])"
        ><p class="eyebrow">{{ item[0] }}</p>
        <h2>{{ t(item[1], item[2]) }}</h2>
        <p>{{ t(item[3], item[4]) }}</p>
        <span class="card-arrow">↗</span></a
      >
    </section>

    <section class="studio-section">
      <div class="shell">
        <div class="section-heading">
          <div>
            <p class="eyebrow">01 / AXONX STUDIO</p>
            <h2>{{ t("研究过程，看得见。", "See your research unfold.") }}</h2>
          </div>
          <a class="text-link" :href="link('getting-started/studio')"
            >{{ t("了解 Studio", "Explore Studio") }} ↗</a
          >
        </div>
        <p class="section-lead">
          {{
            t(
              "从任务运行到结果解读，在同一工作台查看研究证据。",
              "From task execution to result interpretation, inspect your research in one workspace.",
            )
          }}
        </p>
        <div
          class="screen-tabs"
          role="tablist"
          :aria-label="t('Studio 展示', 'Studio showcase')"
        >
          <button
            v-for="(item, index) in screens"
            :id="`screen-tab-${index}`"
            :key="item[0]"
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
            {{ t(item[0], item[1]) }}
          </button>
        </div>
        <div class="screen-carousel">
          <button
            class="screen-arrow screen-arrow-prev"
            type="button"
            :aria-label="t('上一张', 'Previous slide')"
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
              :key="item[0]"
              class="screen-slide"
              role="tabpanel"
              :aria-labelledby="`screen-tab-${index}`"
              :inert="selected !== index"
            >
              <div class="screen-panel">
                <div class="screen-top">
                  <span class="window-dots">● ● ●</span>
                  <span>AXONX STUDIO / {{ item[1].toUpperCase() }}</span>
                  <span class="screen-live">{{
                    t("真实界面", "ACTUAL INTERFACE")
                  }}</span>
                </div>
                <a :href="link(item[3])">
                  <img
                    :src="item[2]"
                    :alt="t(item[0], item[1])"
                    loading="lazy"
                    :width="item[6]"
                    :height="item[7]"
                  />
                </a>
              </div>
              <div class="screen-caption">
                <p>{{ t(item[4], item[5]) }}</p>
                <a class="text-link" :href="link(item[3])">
                  {{ t("阅读指南", "Read the guide") }} ↗
                </a>
              </div>
            </div>
          </div>
          <button
            class="screen-arrow screen-arrow-next"
            type="button"
            :aria-label="t('下一张', 'Next slide')"
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
            {{
              t(
                "研究自由扩展，执行有据可循。",
                "Flexible research. Grounded execution.",
              )
            }}
          </h2>
        </div>
      </div>
      <div class="capabilities">
        <a v-for="item in capabilities" :key="item[0]" :href="link(item[5])"
          ><p class="eyebrow">{{ item[0] }} <span>↗</span></p>
          <h3>{{ t(item[1], item[2]) }}</h3>
          <p>{{ t(item[3], item[4]) }}</p></a
        >
      </div>
    </section>

    <section class="capability-section shell">
      <div class="section-heading">
        <div>
          <p class="eyebrow">03 / CONTINUE YOUR RESEARCH</p>
          <h2>{{ t("按目标深入。", "Continue by goal.") }}</h2>
        </div>
        <a class="text-link" :href="link('docs')"
          >{{ t("文档导航", "Documentation map") }} ↗</a
        >
      </div>
      <div class="capabilities">
        <a v-for="item in journeys" :key="item[0]" :href="link(item[5])">
          <p class="eyebrow">{{ item[0] }} <span>↗</span></p>
          <h3>{{ t(item[1], item[2]) }}</h3>
          <p>{{ t(item[3], item[4]) }}</p>
        </a>
      </div>
    </section>

    <section class="case-study shell">
      <div class="section-heading">
        <div>
          <p class="eyebrow">04 / AGENT RESEARCH CASE</p>
          <h2>
            {{
              t(
                "从插件开发到独立确认。",
                "From plugin development to confirmation.",
              )
            }}
          </h2>
        </div>
        <a class="text-link" :href="link('research/experiments')"
          >{{ t("实验方法", "Experiment design") }} ↗</a
        >
      </div>
      <p class="section-lead">
        {{
          t(
            "Codex 将 Alpha158 扩展为独立插件，通过 AxonX 执行特征消融、锁定方案与独立确认。实验同时记录改善、下降与不确定性，尚未证明稳定增量。",
            "Codex extended Alpha158 as a separate plugin, then used AxonX for feature ablations, configuration locking, and independent confirmation. The experiment records gains, declines, and uncertainty; stable incremental gains remain unproven.",
          )
        }}
      </p>
      <div class="actions">
        <a
          class="action secondary"
          :href="
            link('getting-started/overview') +
            (zh
              ? '#benchmark-agent-开发市场横截面增强特征'
              : '#benchmark-agent-developed-market-cross-sectional-features')
          "
          >{{ t("查看 Benchmark", "Read the benchmark") }} ↗</a
        >
        <a class="text-link" :href="link('plugins/alpha158-enhanced')"
          >{{
            t("特征、参数与复现", "Features, parameters, and reproduction")
          }}
          ↗</a
        >
      </div>
    </section>

    <section class="closing shell">
      <div>
        <p class="eyebrow">BUILD YOUR RESEARCH LOOP</p>
        <h2>{{ t("从一个 Task 开始。", "Start with one Task.") }}</h2>
        <p>
          {{
            t(
              "内置 demo 无需外部数据或模型凭据。",
              "The built-in demo needs no external data or model credentials.",
            )
          }}
        </p>
      </div>
      <div class="actions">
        <a class="action primary" :href="link('getting-started/quickstart')"
          >{{ t("运行 Demo", "Run the demo") }} →</a
        ><a class="action secondary" :href="link('docs')"
          >{{ t("浏览全部文档", "Browse all docs") }} ↗</a
        >
      </div>
    </section>
  </main>
</template>
