"""Resolve and cache explicit lazy package exports."""

from importlib import import_module


def lazy_export(namespace: dict, name: str, exports: dict):
    try:
        module, symbol = exports[name]
    except KeyError:
        raise AttributeError(f"module {namespace['__name__']!r} has no attribute {name!r}") from None
    value = getattr(import_module(f".{module}", namespace["__name__"]), symbol)
    namespace[name] = value
    return value
