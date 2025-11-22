#
# Copyright © 2025-10-07 22:38:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

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
            else:
                return x

        self.args = make_immutable(args)
        self.kwargs = make_immutable(kwargs)
        self.hash = hash((self.args, self.kwargs))

    def __hash__(self) -> int:
        return self.hash

    def __str__(self) -> str:
        full_str = f"args={self.args}, kwargs={self.kwargs}"
        if len(full_str) > 30:
            full_str = full_str[:27] + "..."
        return full_str
