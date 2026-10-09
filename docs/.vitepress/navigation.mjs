// Each page has one navigation owner; cross-links connect reader journeys.
export const groups = [
  {
    id: "docs",
    labels: ["开始使用", "Get started"],
    page: "docs",
    sections: [
      [
        "入门路径",
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
          "concepts/architecture",
          "concepts/jobs-and-tasks",
          "concepts/task-lifecycle",
          "concepts/task-lineage",
          "concepts/workspace",
        ],
      ],
      ["常见问题", "FAQ", ["faq"]],
    ],
  },
  {
    id: "research",
    labels: ["量化研究", "Research"],
    page: "research/overview",
    sections: [
      [
        "研究流程",
        "Research workflow",
        [
          "research/overview",
          "research/workflow",
          "research/tushare",
          "research/results",
        ],
      ],
      [
        "实验与评估",
        "Experiments & evaluation",
        [
          "research/experiments",
          "research/backtest",
          "research/strategy-comparison",
        ],
      ],
      [
        "研究插件",
        "Research plugins",
        [
          "plugins/management",
          "plugins/alpha158",
          "plugins/alpha158-factor",
          "plugins/alpha158-strategy",
        ],
      ],
    ],
  },
  {
    id: "agent",
    labels: ["Agent", "Agent"],
    page: "agent/overview",
    sections: [
      ["选择接入方式", "Choose an integration", ["agent/overview"]],
      [
        "外部 Agent",
        "External agents",
        ["agent/external", "agent/mcp-integration"],
      ],
      ["内置 Agent", "Built-in agent", ["agent/configuration", "agent/usage"]],
    ],
  },
  {
    id: "operations",
    labels: ["运行与部署", "Operations"],
    page: "guides/overview",
    sections: [
      ["运行总览", "Operations overview", ["guides/overview"]],
      [
        "任务与文件",
        "Tasks & files",
        [
          "guides/task-management",
          "guides/composite-tasks",
          "guides/workspace-files",
          "guides/task-sync",
        ],
      ],
      [
        "服务与机器",
        "Services & machines",
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
        ["guides/scheduling", "research/notifications", "guides/operations"],
      ],
    ],
  },
  {
    id: "reference",
    labels: ["接口参考", "Reference"],
    page: "reference/overview",
    sections: [
      ["参考总览", "Reference overview", ["reference/overview"]],
      [
        "CLI、Python 与配置",
        "CLI, Python & configuration",
        [
          "reference/cli",
          "reference/python",
          "reference/client-configuration",
          "reference/configuration",
        ],
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
    ],
  },
  {
    id: "developers",
    labels: ["开发扩展", "Developers"],
    page: "development/overview",
    sections: [
      [
        "开发指南",
        "Development guides",
        [
          "development/overview",
          "development/contributing",
          "dev_guide",
          "development/framework-extensions",
          "development/studio",
        ],
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
];

export const groupRoutes = (group) =>
  group.sections.flatMap(([, , pages]) => pages);
