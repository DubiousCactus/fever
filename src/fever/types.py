#
# Copyright © 2025-10-07 22:38:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

import warnings
from collections.abc import Iterable
from copy import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np


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
            elif isinstance(x, np.ndarray):
                return x.tobytes()
            else:
                return x

        def hash_or_hash(x: Any) -> int:
            h = -1
            if isinstance(x, Iterable) and not isinstance(x, str):
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


class FeverRegistryError(Exception):
    def __str__(self) -> str:
        return "FeverRegistryError: " + super().__str__()
