import type { Language, PageId, TaskState } from "./types";

const shared = {
  zh: {
    brandTag: "COMPUTE · RESEARCH · DEPLOY", studio: "控制台", serviceOnline: "服务在线", serviceOffline: "服务未连接",
    pages: { machines: "机器资源", tasks: "Task 管理", submit: "提交 Task", rawData: "原始数据", factors: "因子分析", training: "模型训练", prediction: "模型预测", backtest: "模型回测" } as Record<PageId, string>,
    taskTitle: "任务运行中心", taskLead: "观察每一次计算，从排队到产出。", refreshNow: "立即刷新", autoRefresh: "自动刷新", nextRefresh: "{seconds} 秒后刷新",
    search: "搜索 Task ID、类型或 PID", allStates: "全部状态", allTypes: "全部类型", total: "全部任务", active: "进行中", succeeded: "已成功", attention: "需关注",
    taskId: "TASK ID", type: "类型", state: "状态", progress: "进度", started: "开始时间", duration: "耗时", action: "操作", details: "详情", cancel: "取消", cancelling: "取消中",
    noTasks: "暂无运行记录", noTasksHint: "提交一个 Task 后，状态会自动出现在这里。", noMatches: "没有符合筛选条件的任务", requestFailed: "无法读取任务状态", staleHint: "当前显示最近一次成功获取的数据。", retry: "重试",
    taskDetails: "Task 详情", close: "关闭", process: "进程", timeline: "时间线", steps: "执行步骤", result: "输出结果", error: "错误信息", logPath: "日志路径", noResult: "暂无输出", notStarted: "尚未开始", cancelConfirm: "确定取消这个运行中的 Task？", confirmCancel: "确认取消",
    submitTitle: "启动一个新任务", submitLead: "选择已安装的 Task，配置参数，然后交给 AxonX 独立执行。", taskCatalog: "已安装 TASK", tasksAvailable: "{count} 个可用", findTask: "搜索已安装 Task", configure: "运行配置", output: "预期输出", required: "必填", optional: "选填", choose: "请选择", jsonHint: "请输入合法 JSON", submit: "提交运行", submitting: "正在提交", submitted: "任务已交给 AxonX", submittedHint: "工作进程启动后，运行状态会自动出现在 Task 管理页。", viewTasks: "查看任务状态", catalogFailed: "无法读取已安装的 Task", noInstalled: "没有发现已安装的 Task",
    comingSoon: "正在接入", comingHint: "此工作区已经预留，后续能力将在这里展开。", appearance: "外观", system: "跟随系统", light: "浅色", dark: "深色",
    machineTitle: "机器资源", machineLead: "实时掌握本机与远端计算节点的资源水位。", cluster: "计算集群", nodesOnline: "在线节点", cpuCapacity: "CPU 核心", memoryCapacity: "总内存", gpuCapacity: "GPU 设备", localNode: "本机", remoteNode: "远端", nodeList: "计算节点", nodeCount: "{count} 个节点", online: "在线", offline: "离线", liveMetrics: "实时资源", machineLoading: "正在读取计算资源…", cpuUsage: "CPU 使用率", memoryUsage: "内存使用率", coresUsed: "已用核心", available: "可用", totalCores: "逻辑核心", physicalCores: "物理核心", usedMemory: "已使用", totalMemory: "总容量", gpuResources: "GPU 资源", noGpu: "当前平台未提供 GPU 指标", noGpuHint: "macOS 或虚拟化环境可能无法提供稳定的 GPU 指标。", gpuUtilization: "计算使用率", gpuMemory: "显存使用率", runtimeInfo: "运行环境", version: "AxonX 版本", gitCommit: "Git Commit", endpoint: "服务地址", lastUpdated: "最后更新", machineUnavailable: "此节点当前不可访问", machineFailed: "无法读取机器资源", selectNode: "选择一个节点查看资源详情",
    states: { queued: "排队中", running: "运行中", succeeded: "成功", failed: "失败", cancelled: "已取消" } as Record<TaskState, string>,
    types: { ingestion: "数据摄取", etl: "数据处理", analysis: "分析", training: "训练", inference: "预测", backtest: "回测" } as Record<string, string>,
  },
  en: {
    brandTag: "COMPUTE · RESEARCH · DEPLOY", studio: "Studio", serviceOnline: "Service online", serviceOffline: "Service unavailable",
    pages: { machines: "Machines", tasks: "Tasks", submit: "Submit Task", rawData: "Raw Data", factors: "Factor Analysis", training: "Training", prediction: "Prediction", backtest: "Backtest" } as Record<PageId, string>,
    taskTitle: "Task operations", taskLead: "Follow every compute run from queue to output.", refreshNow: "Refresh now", autoRefresh: "Auto refresh", nextRefresh: "Refresh in {seconds}s",
    search: "Search Task ID, type, or PID", allStates: "All states", allTypes: "All types", total: "All tasks", active: "In progress", succeeded: "Succeeded", attention: "Needs attention",
    taskId: "TASK ID", type: "TYPE", state: "STATUS", progress: "PROGRESS", started: "STARTED", duration: "DURATION", action: "ACTION", details: "Details", cancel: "Cancel", cancelling: "Cancelling",
    noTasks: "No task runs yet", noTasksHint: "Submit a Task and its status will appear here automatically.", noMatches: "No tasks match these filters", requestFailed: "Unable to load task status", staleHint: "Showing the last successfully loaded data.", retry: "Retry",
    taskDetails: "Task details", close: "Close", process: "Process", timeline: "Timeline", steps: "Execution steps", result: "Output", error: "Error", logPath: "Log path", noResult: "No output yet", notStarted: "Not started", cancelConfirm: "Cancel this running Task?", confirmCancel: "Cancel Task",
    submitTitle: "Launch a new task", submitLead: "Choose an installed Task, configure its inputs, and hand it to AxonX for isolated execution.", taskCatalog: "INSTALLED TASKS", tasksAvailable: "{count} available", findTask: "Search installed Tasks", configure: "Run configuration", output: "Expected output", required: "Required", optional: "Optional", choose: "Choose an option", jsonHint: "Enter valid JSON", submit: "Submit run", submitting: "Submitting", submitted: "Task handed to AxonX", submittedHint: "Its runtime status will appear in Task management after the worker starts.", viewTasks: "View task status", catalogFailed: "Unable to load installed Tasks", noInstalled: "No installed Tasks found",
    comingSoon: "Integration in progress", comingHint: "This workspace is reserved for the next AxonX capability.", appearance: "Appearance", system: "System", light: "Light", dark: "Dark",
    machineTitle: "Machine resources", machineLead: "Monitor capacity across local and remote compute nodes in real time.", cluster: "Compute cluster", nodesOnline: "Nodes online", cpuCapacity: "CPU cores", memoryCapacity: "Total memory", gpuCapacity: "GPU devices", localNode: "Local", remoteNode: "Remote", nodeList: "COMPUTE NODES", nodeCount: "{count} nodes", online: "Online", offline: "Offline", liveMetrics: "Live resources", machineLoading: "Loading compute resources…", cpuUsage: "CPU usage", memoryUsage: "Memory usage", coresUsed: "Cores used", available: "Available", totalCores: "Logical cores", physicalCores: "Physical cores", usedMemory: "Used memory", totalMemory: "Total capacity", gpuResources: "GPU resources", noGpu: "GPU metrics are unavailable on this platform", noGpuHint: "macOS or virtualized environments may not expose stable GPU telemetry.", gpuUtilization: "Compute usage", gpuMemory: "Memory usage", runtimeInfo: "Runtime", version: "AxonX version", gitCommit: "Git commit", endpoint: "Endpoint", lastUpdated: "Last updated", machineUnavailable: "This node is currently unreachable", machineFailed: "Unable to load machine resources", selectNode: "Select a node to inspect its resources",
    states: { queued: "Queued", running: "Running", succeeded: "Succeeded", failed: "Failed", cancelled: "Cancelled" } as Record<TaskState, string>,
    types: { ingestion: "Ingestion", etl: "ETL", analysis: "Analysis", training: "Training", inference: "Inference", backtest: "Backtest" } as Record<string, string>,
  },
} as const;

export const t = (language: Language) => shared[language];
export const interpolate = (value: string, params: Record<string, string | number>) =>
  Object.entries(params).reduce((result, [key, item]) => result.replace(`{${key}}`, String(item)), value);
