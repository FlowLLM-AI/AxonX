// Every document belongs to exactly one top-level tab.
export const groups = [
  {
    id: "docs",
    labels: ["文档", "Docs"],
    page: "docs",
    sections: [
      ["文档导航", "Documentation", ["docs"]],
      [
        "开始使用",
        "Getting started",
        ["getting-started/overview", "getting-started/quickstart"],
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
      [
        "日常操作",
        "Task operations",
        [
          "guides/task-management",
          "guides/workspace-files",
          "guides/remote-machines",
          "guides/task-sync",
          "guides/scheduling",
        ],
      ],
      [
        "部署与运维",
        "Deployment & operations",
        [
          "guides/authentication",
          "guides/deployment",
          "guides/http-proxy",
          "guides/operations",
        ],
      ],
      [
        "CLI 与配置",
        "CLI & configuration",
        [
          "reference/cli",
          "reference/client-configuration",
          "reference/configuration",
        ],
      ],
      ["常见问题", "FAQ", ["faq"]],
    ],
  },
  {
    id: "plugins",
    labels: ["插件", "Plugins"],
    page: "plugins/management",
    sections: [
      [
        "插件",
        "Plugins",
        ["plugins/management", "plugins/alpha158", "plugins/alpha158-enhanced"],
      ],
    ],
  },
  {
    id: "research",
    labels: ["量化研究", "Research"],
    page: "research/workflow",
    sections: [
      [
        "量化研究",
        "Quant research",
        [
          "research/workflow",
          "research/tushare",
          "research/results",
          "research/backtest",
          "research/strategy-comparison",
          "research/notifications",
        ],
      ],
    ],
  },
  {
    id: "studio",
    labels: ["Studio", "Studio"],
    page: "getting-started/studio",
    sections: [
      ["Studio", "Studio", ["getting-started/studio", "development/studio"]],
    ],
  },
  {
    id: "agent",
    labels: ["Agent", "Agent"],
    page: "agent/configuration",
    sections: [
      [
        "Agent",
        "Agent",
        ["agent/configuration", "agent/usage", "agent/mcp-integration"],
      ],
      ["Agent API", "Agent API", ["api/agent"]],
    ],
  },
  {
    id: "developers",
    labels: ["开发者", "Developers"],
    page: "development/framework-extensions",
    sections: [
      [
        "开发指南",
        "Development guides",
        [
          "development/contributing",
          "dev_guide",
          "development/framework-extensions",
        ],
      ],
      [
        "API 与事件",
        "API & events",
        [
          "api/overview",
          "api/tasks",
          "api/events",
          "api/workspace",
          "api/machines",
          "api/plugins-sync",
        ],
      ],
      [
        "Python 与扩展协议",
        "Python & extension contracts",
        [
          "reference/python",
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
