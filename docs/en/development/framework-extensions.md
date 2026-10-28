# Framework Extensions

## Choosing an extension point

Tasks own synchronous research, Component owns managed reusable resources, BaseStep adapts an asynchronous Job operation, and the host owns process supervision. Task-only plugin manifests do not register application providers. Supply those through Application(providers=...) and config.

## Providers and local registries

`@provider("backend")` declares a provider name without mutating global state. ProviderRegistry maps component_type/backend to classes in one application, rejects conflicts and freezes after composition. Import BaseComponent from app.components.base, BaseStep from app.steps.base and provider from app.components.registry.

## Runnable Step and Job example

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

## Declaring component dependencies

A BaseComponent calls `self.depend("attribute", "instance", ExpectedBase)` during construction. The application validates category/type, injects the selected object and orders startup/closure. BaseStep accesses a configured capability with `self.component(ExpectedBase)`. Step invocation state is copied per Job run by PipelineJob; do not share mutable invocation state through global objects.

## Parameters, defaults and system

Job parameters are an object JSON schema. Defaults merge before schema validation. Step injected_parameters describe system-owned context separately; callers cannot forge injected keys. Configured step options select backends/components, not public caller fields. Use the JobContext mapping and response through self.context and self.response.

## Events and results

Await self.emit(event) for backpressure. Import events from axonx.client.events and Task progress/log types from task.models.events. A Job yields one terminal ResultEvent; nonstreaming execution folds to the same JobResponse. Always close asynchronous event sources when consumption stops early.

## Host integration

Inject task_catalog for definition Jobs, updates for update control, launch_scheduled for Cron. Application does not discover/install plugins or launch processes implicitly. The CLI daemon launcher assembles these dependencies. An embedded app without a host update backend cannot restart itself through an update Job.

## Task composition and research bases

Use BaseTask.run_task for synchronous children. TaskExecutor owns lifecycle and cleanup; caller coordination protects same-name directories. Use core.windows and an injected clock for windowed work, storage.online for immutable online publication and verified history. For stock portfolios inherit task.builtins.stock.backtest.BaseStockBacktestTask and provide universes/selectors; do not reproduce accounting in UI.

## Verification scope

Test provider composition, public schema validation, startup rollback, cleanup/cancellation, stream result and resource ownership. Run the standalone example above. Protocol security and process ownership are application boundaries, not a sandbox for arbitrary plugin code.

Sources: [composition](../../../axonx/app/core/composition.py), [registry](../../../axonx/app/components/registry.py), [Step](../../../axonx/app/steps/base.py).
