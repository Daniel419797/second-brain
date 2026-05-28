"""Tiny lazy-import helpers for startup-sensitive modules."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any, Callable


class LazyModule:
    """Proxy a module until one of its attributes is actually used."""

    def __init__(self, module_name: str):
        self._module_name = module_name
        self._module: ModuleType | None = None

    def _load(self) -> ModuleType:
        if self._module is None:
            self._module = importlib.import_module(self._module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        return getattr(self._load(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"_module_name", "_module"}:
            object.__setattr__(self, name, value)
        else:
            setattr(self._load(), name, value)

    def __repr__(self) -> str:
        state = "loaded" if self._module is not None else "pending"
        return f"<LazyModule {self._module_name} ({state})>"


def lazy_module(module_name: str) -> LazyModule:
    return LazyModule(module_name)


def lazy_callable(module_name: str, attribute: str) -> Callable[..., Any]:
    def _call(*args: Any, **kwargs: Any) -> Any:
        return getattr(importlib.import_module(module_name), attribute)(*args, **kwargs)

    _call.__name__ = attribute
    _call.__qualname__ = f"{module_name}.{attribute}"
    return _call
