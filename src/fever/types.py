#
# Copyright © 2025-10-07 22:38:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

import warnings
from collections.abc import Iterable
from copy import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class FeverWarning(Warning):
    pass


@dataclass
class FeverClass:
    name: str
    obj: object
    hash: int
    code: str

    def __hash__(self) -> int:
        return self.hash


@dataclass
class FeverFunction:
    name: str
    args: List[Any]
    obj: object
    hash: int
    code: str

    def __hash__(self) -> int:
        return self.hash


@dataclass
class FeverLambda:
    args: List[Any]
    obj: Optional[object] = None


@dataclass
class FeverImport:
    module: str
    code: str
    alias: Optional[str] = None
    sub_imports: Optional[List[str]] = None


@dataclass
class FeverGlobalVar:
    name: str
    value: Any


@dataclass
class FeverModule:
    name: str
    obj: object
    classes: List[FeverClass]
    functions: List[FeverFunction]
    methods: Dict[FeverClass, List[FeverFunction]]
    lambdas: List[FeverLambda]
    imports: List[FeverImport]
    globals: List[FeverGlobalVar]


class FeverParameters:
    __slots__ = "args", "kwargs", "hash"

    def __init__(self, args: tuple, kwargs: dict):
        def is_torch_tensor(x: Any) -> bool:
            try:
                import torch

                return isinstance(x, torch.Tensor)
            except ImportError:
                return False

        def make_immutable(x: Any) -> object:
            if isinstance(x, dict):
                return frozenset(
                    {make_immutable(k): make_immutable(v) for k, v in x.items()}
                )
            elif isinstance(x, list):
                return tuple([make_immutable(a) for a in x])
            elif isinstance(x, set):
                return frozenset([make_immutable(a) for a in x])
            elif isinstance(x, tuple):
                return tuple([make_immutable(a) for a in x])
            elif hasattr(x, "tobytes"):
                try:
                    return x.tobytes()
                except Exception:
                    try:
                        return x.tobytes
                    except Exception:
                        return str(x)
            elif is_torch_tensor(x):
                import torch

                try:
                    return torch.hash_tensor(x).item()
                except Exception:
                    return tuple([make_immutable(a) for a in x.tolist()])
            else:
                return x

        # Source - https://stackoverflow.com/a/17795199
        # Posted by glarrain, modified by community. See post 'Timeline' for change history
        # Retrieved 2026-02-15, License - CC BY-SA 4.0
        def is_builtin_class_instance(obj):
            return obj.__class__.__module__ == "builtins"

        def hash_or_hash(x: Any) -> int:
            h = -1
            if (
                is_builtin_class_instance(x)
                and isinstance(x, Iterable)
                and not isinstance(x, str)
            ):
                for y in x:
                    res = hash_or_hash(y)
                    h += res
                return h
            try:
                h = hash(x)
            except Exception:
                h = hash(make_immutable(x))
            return h

        self.args = copy(args)
        self.kwargs = copy(kwargs)
        try:
            self.hash = hash((hash_or_hash(args), hash_or_hash(kwargs)))
        except TypeError:
            warnings.warn(
                f"Could not hash parameters: args={self.args}, kwargs={self.kwargs}",
                FeverWarning,
            )
            self.hash = -1

    def __hash__(self) -> int:
        return self.hash

    def __str__(self) -> str:
        full_str = f"args={self.args}, kwargs={self.kwargs}"
        if len(full_str) > 30:
            full_str = full_str[:27] + "..."
        return full_str

    def __len__(self) -> int:
        args_len = 1
        if isinstance(self.args, Iterable):
            args_len = len(self.args)
        kwargs_len = len(self.kwargs)
        return args_len + kwargs_len


class FeverEntryPoint:
    pass


class TraceNode:
    __slots__ = "module", "func", "params_hash"

    def __init__(
        self, module: str, func: str | object, params_hash: Optional[int] = None
    ):
        self.module = module
        self.func = func
        self.params_hash = params_hash

    @staticmethod
    def strip_params(node: "TraceNode") -> "TraceNode":
        return TraceNode(copy(node.module), copy(node.func))

    def __str__(self) -> str:
        if self.params_hash is None:
            return f"{self.module}.{self.func}"
        else:
            return f"{self.module}.{self.func}(0x{hex(self.params_hash)[-5:]})"

    def equals_ignore_params(self, other: "TraceNode") -> bool:
        return self.module == other.module and self.func == other.func

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TraceNode):
            return False
        return (
            self.module == other.module
            and self.func == other.func
            and self.params_hash == other.params_hash
        )

    def __hash__(self) -> int:
        return hash((self.module, self.func, self.params_hash))


class FeverRegistryError(Exception):
    def __str__(self) -> str:
        return "FeverRegistryError: " + super().__str__()


class FeverTrackerError(Exception):
    def __str__(self) -> str:
        return "FeverTrackerError: " + super().__str__()
