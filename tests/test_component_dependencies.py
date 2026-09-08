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

    with pytest.raises(ValueError, match="unresolved due to circular dependencies"):
        await app.start()


async def test_independent_components_keep_configuration_order():
    events = []

    class Probe(BaseComponent):
        component_type = "test_probe"

        async def _start(self):
            events.append(self.name)

    with R.preserve(allow_mutation=True):
        R.register(Probe, "test")
        app = Application(
            components={
                "test_probe": {
                    "z-last-alphabetically": {"backend": "test"},
                    "a-first-alphabetically": {"backend": "test"},
                },
            },
        )

    await app.start()
    assert events == ["z-last-alphabetically", "a-first-alphabetically"]
    await app.close()


async def test_dependency_failure_does_not_close_unstarted_parent():
    class Provider(BaseComponent):
        component_type = "test_provider"

    class Consumer(BaseComponent):
        component_type = "test_consumer"

        def __init__(self):
            super().__init__()
            self.provider = self.bind("missing", Provider, optional=False)
            self.close_count = 0

        async def _close(self):
            self.close_count += 1

    consumer = Consumer()
    with pytest.raises(ValueError, match="Missing component dependency"):
        await consumer.start()
    assert consumer.close_count == 0


async def test_owned_close_failure_does_not_skip_remaining_cleanup():
    class Owned(BaseComponent):
        component_type = "test_owned"

        def __init__(self, *, fail_close=False):
            super().__init__()
            self.fail_close = fail_close

        async def _close(self):
            if self.fail_close:
                raise RuntimeError("close failed")

    class Parent(BaseComponent):
        component_type = "test_parent"

        def __init__(self, first, second):
            super().__init__()
            self.first = self.bind("first", Owned, default_factory=lambda: first)
            self.second = self.bind("second", Owned, default_factory=lambda: second)

    first = Owned()
    second = Owned(fail_close=True)
    parent = Parent(first, second)
    await parent.start()

    with pytest.raises(RuntimeError, match="close failed"):
        await parent.close()
    assert not parent.is_started
    assert not first.is_started
    assert not second.is_started


async def test_multiple_owned_close_failures_are_grouped():
    class Broken(BaseComponent):
        component_type = "test_broken"

        def __init__(self, message):
            super().__init__()
            self.message = message

        async def _close(self):
            raise RuntimeError(self.message)

    class Parent(BaseComponent):
        component_type = "test_parent"

        def __init__(self):
            super().__init__()
            self.first = self.bind("first", Broken, default_factory=lambda: Broken("first"))
            self.second = self.bind("second", Broken, default_factory=lambda: Broken("second"))

    parent = Parent()
    await parent.start()

    with pytest.raises(ExceptionGroup, match="Component cleanup failed") as exc_info:
        await parent.close()
    assert {str(error) for error in exc_info.value.exceptions} == {"first", "second"}
