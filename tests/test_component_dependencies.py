"""Component dependency resolution and lifecycle ordering."""

import pytest

from axonx import Application, BaseComponent
from axonx.components import R


def component_classes(events):
    class Provider(BaseComponent):
        component_type = "test_provider"

        async def _start(self):
            events.append("start:provider")

        async def _close(self):
            events.append("close:provider")

    class Consumer(BaseComponent):
        component_type = "test_consumer"

        def __init__(self, provider="default", **kwargs):
            super().__init__(**kwargs)
            self.provider = self.bind(provider, Provider, optional=False)

        async def _start(self):
            assert self.provider.is_started
            events.append("start:consumer")

        async def _close(self):
            events.append("close:consumer")

    return Provider, Consumer


async def test_dependencies_control_startup_and_shutdown_order():
    events = []
    provider, consumer = component_classes(events)
    with R.preserve(allow_mutation=True):
        R.register(provider, "test")
        R.register(consumer, "test")
        app = Application(
            components={
                "test_consumer": {"default": {"backend": "test"}},
                "test_provider": {"default": {"backend": "test"}},
            },
        )

    await app.start()
    assert events == ["start:provider", "start:consumer"]
    assert app.context.components["test_consumer"]["default"].provider is app.context.components[
        "test_provider"
    ]["default"]

    await app.close()
    assert events == ["start:provider", "start:consumer", "close:consumer", "close:provider"]


async def test_missing_required_dependency_is_rejected_before_startup():
    events = []
    _, consumer = component_classes(events)
    with R.preserve(allow_mutation=True):
        R.register(consumer, "test")
        app = Application(components={"test_consumer": {"default": {"backend": "test"}}})

    with pytest.raises(ValueError, match="depends on missing test_provider:default"):
        await app.start()
    assert events == []


async def test_circular_dependencies_are_rejected():
    class First(BaseComponent):
        component_type = "test_first"

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.second = self.bind("default", Second, optional=False)

    class Second(BaseComponent):
        component_type = "test_second"

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.first = self.bind("default", First, optional=False)

    with R.preserve(allow_mutation=True):
        R.register(First, "test")
        R.register(Second, "test")
        app = Application(
            components={
                "test_first": {"default": {"backend": "test"}},
                "test_second": {"default": {"backend": "test"}},
            },
        )

    with pytest.raises(ValueError, match="Circular component dependency"):
        await app.start()
