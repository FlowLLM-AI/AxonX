"""Import qualified Python symbols while containing registry side effects."""

from importlib import import_module, invalidate_caches, reload
import sys
from types import ModuleType
from typing import Any, TypeVar, cast

from ..components.registry import R

T = TypeVar("T")


def load_symbol(
    target: str,
    expected_base: type[T],
    *,
    kind: str,
    modules: dict[str, ModuleType] | None = None,
) -> type[T]:
    """Load ``module:qualname`` once per module cache and validate its base class."""
    try:
        module_name, qualname = target.split(":", 1)
    except ValueError:
        raise ValueError(f"Invalid {kind} target: {target!r}") from None
    if not module_name or not qualname:
        raise ValueError(f"Invalid {kind} target: {target!r}")

    cache = modules if modules is not None else {}
    invalidate_caches()
    with R.preserve(allow_mutation=True):
        module = cache.get(module_name)
        if module is None:
            loaded = sys.modules.get(module_name)
            module = reload(loaded) if loaded is not None else import_module(module_name)
            cache[module_name] = module
        value: Any = module
        for part in qualname.split("."):
            value = getattr(value, part)

    if not isinstance(value, type) or not issubclass(value, expected_base):
        raise TypeError(f"{kind} target must subclass {expected_base.__name__}: {target}")
    return cast(type[T], value)
