// Each page has one navigation owner; cross-links connect reader journeys.
export const groups = [
  {
    id: "docs",
    labels: ["开始使用", "Get started"],
    page: "docs",
    sections: [
      [
        "首次上手",
        "Start here",
        [
          "docs",
          "getting-started/overview",
          "getting-started/quickstart",
          "getting-started/studio",
        ],
      ],
      [
        "核心概念",
        "Core concepts",
        [
          "concepts/jobs-and-tasks",
          "concepts/task-lifecycle",
          "concepts/workspace",
          "concepts/task-lineage",
          "concepts/architecture",
        ],
      ],
      ["帮助", "Help", ["faq"]],
    ],
  },
  {
    id: "agent",
    labels: ["Agent 开发", "Agent development"],
    page: "agent/overview",
    sections: [
      [
        "开始开发",
        "Start developing",
        ["agent/overview", "agent/research-prompt"],
      ],
      [
        "外部 Agent",
        "External agents",
        ["agent/external", "agent/mcp-integration"],
      ],
      ["内置 Agent", "Built-in agent", ["agent/configuration", "agent/usage"]],
    ],
  },
  {
    id: "research",
    labels: ["量化研究", "Research"],
    page: "research/overview",
    sections: [
      [
        "运行基线",
        "Run a baseline",
        ["research/overview", "research/tushare", "research/workflow"],
      ],
      [
        "开发研究插件",
        "Develop research plugins",
        ["dev_guide", "plugins/management"],
      ],
      [
        "插件实例",
        "Plugin examples",
        ["plugins/qlib-a158", "plugins/qlib-factor", "plugins/qlib-strategy"],
      ],
      [
        "评估与证据",
        "Evaluation & evidence",
        [
          "research/results",
          "research/backtest",
          "research/strategy-comparison",
          "research/experiments",
        ],
      ],
      ["研究案例", "Case study", ["research/alpha158-case"]],
    ],
  },
  {
    id: "operations",
    labels: ["运行与部署", "Operations"],
    page: "guides/overview",
    sections: [
      [
        "日常执行",
        "Daily execution",
        [
          "guides/overview",
          "guides/task-management",
          "guides/composite-tasks",
          "guides/workspace-files",
        ],
      ],
      [
        "执行环境",
        "Execution environments",
        [
          "guides/authentication",
          "guides/deployment",
          "guides/remote-machines",
          "guides/http-proxy",
        ],
      ],
      [
        "自动化与维护",
        "Automation & maintenance",
        [
          "guides/scheduling",
          "research/notifications",
          "guides/task-sync",
          "guides/operations",
        ],
      ],
    ],
  },
  {
    id: "reference",
    labels: ["参考手册", "Reference"],
    page: "reference/overview",
    sections: [
      [
        "调用接口",
        "Interfaces",
        ["reference/overview", "reference/cli", "reference/python"],
      ],
      [
        "HTTP API 与事件",
        "HTTP APIs & events",
        [
          "api/overview",
          "api/tasks",
          "api/events",
          "api/workspace",
          "api/machines",
          "api/plugins-sync",
          "api/agent",
        ],
      ],
      [
        "配置",
        "Configuration",
        ["reference/client-configuration", "reference/configuration"],
      ],
      [
        "扩展契约",
        "Extension contracts",
        [
          "reference/task-contracts",
          "reference/plugin-manifest",
          "reference/research-artifacts",
        ],
      ],
    ],
  },
  {
    id: "developers",
    labels: ["开发与贡献", "Contributing"],
    page: "development/overview",
    sections: [
      [
        "框架与 Studio",
        "Framework & Studio",
        [
          "development/overview",
          "development/contributing",
          "development/framework-extensions",
          "development/studio",
        ],
      ],
    ],
  },
];

export const groupRoutes = (group) =>
  group.sections.flatMap(([, , pages]) => pages);
