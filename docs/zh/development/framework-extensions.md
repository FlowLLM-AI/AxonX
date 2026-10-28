# 框架扩展

## 选择扩展点

Task 负责同步研究，Component 负责受管理的可复用资源，BaseStep 适配异步 Job 操作，宿主负责进程监督。Task manifest 不注册应用 provider，应通过 Application(providers=...) 和配置提供。

## Provider 与局部 Registry

`@provider("backend")` 声明名称，不修改全局状态。ProviderRegistry 在单个应用中将 component_type/backend 映射到类，拒绝冲突并在装配后冻结。BaseComponent 位于 app.components.base，BaseStep 位于 app.steps.base，provider 位于 app.components.registry。

## 可运行的 Step 与 Job 示例

```python
import asyncio
from axonx.app.core.application import Application
from axonx.app.components.registry import provider
from axonx.app.steps.base import BaseStep

@provider("greeting")
class GreetingStep(BaseStep):
    async def execute(self):
        self.response.answer = {"message": f"Hello, {self.context['name']}"}

async def main():
    async with Application(
        providers=[GreetingStep], log_to_console=False, log_to_file=False,
        jobs={"greet": {
            "parameters": {
                "type": "object", "properties": {"name": {"type": "string"}},
                "required": ["name"], "additionalProperties": False,
            },
            "steps": [{"backend": "greeting"}],
        }},
    ) as app:
        response = await app.run_job("greet", {"name": "AxonX"})
        assert response.success
        print(response.answer)

asyncio.run(main())
```

## 声明组件依赖

BaseComponent 构造时调用 `self.depend("attribute", "instance", ExpectedBase)`，应用检查类别/类型、注入对象并安排启动/关闭顺序。BaseStep 用 `self.component(ExpectedBase)` 访问已配置能力。PipelineJob 每次调用复制 Step 状态，不应通过全局对象共享可变调用状态。

## 参数、默认值与系统字段

Job parameters 是对象 JSON Schema，默认值在校验前合并。Step injected_parameters 单独描述系统上下文，调用方不能伪造注入键。配置中的 Step 选项选择后端/组件，不是公共参数。通过 self.context 使用 JobContext 映射，通过 self.response 写响应。

## 事件与结果

await self.emit(event) 提供背压。事件从 axonx.client.events 导入，Task 进度/日志类型来自 task.models.events。Job 产生一个终态 ResultEvent，非流式调用折叠成相同 JobResponse。提前结束消费时应关闭异步事件源。

## 宿主集成

定义查询注入 task_catalog，更新注入 updates，Cron 注入 launch_scheduled。Application 不隐式发现/安装插件或启动进程，CLI Daemon 启动层负责装配。没有宿主更新后端的嵌入式应用不能通过更新 Job 自行重启。

## Task 组合与研究基类

同步子任务使用 BaseTask.run_task。TaskExecutor 管理生命周期和清理，同名目录由调用方协调。窗口工作使用 core.windows 和注入时钟，不可变在线发布和核验历史使用 storage.online。股票组合继承 task.builtins.stock.backtest.BaseStockBacktestTask 并提供范围/选择器，UI 不重复实现记账。

## 验证范围

验证 provider 装配、公共 Schema、启动回滚、清理/取消、终态事件和资源所有权，并执行上面的独立示例。协议认证和进程所有权是应用边界，不是任意插件代码的安全沙箱。

源码：[装配](../../../axonx/app/core/composition.py)、[registry](../../../axonx/app/components/registry.py)、[Step](../../../axonx/app/steps/base.py)。
