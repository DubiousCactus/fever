#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-05 16:48:18 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

import ast
import inspect
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List
from uuid import UUID, uuid1

from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.syntax import Syntax


@dataclass
class MitaineClass:
    name: str
    uid: UUID
    ast_node: ast.ClassDef


@dataclass
class MitaineFunction:
    name: str
    uid: UUID
    ast_node: ast.FunctionDef
    args: List[Any]


@dataclass
class MitaineLambda:
    uid: UUID
    ast_node: ast.Lambda
    args: List[Any]


@dataclass
class MitaineModule:
    root: str
    classes: List[MitaineClass]
    functions: List[MitaineFunction]
    methods: Dict[MitaineClass, List[MitaineFunction]]
    lambdas: List[MitaineLambda]


class ASTAnalyzer(ast.NodeVisitor):
    def __init__(self, console: Console):
        self._console = console
        self._current_class = deque()
        self._context = {}

    def _reset_context(self):
        self._context = {
            "classes": [],
            "functions": [],
            "lambdas": [],
            "methods": defaultdict(list),
        }

    def analyze(self, obj: object, name: str, show_ast=False) -> MitaineModule:
        """
        Analyze the AST of a given object (typically a module, but possibly a class or
        other) and return a MitaineModule which tracks module-level functions, classes,
        lambdas and methods.
        """
        self._reset_context()
        source = inspect.getsource(obj)
        self._console.print(
            Panel(
                Syntax(source, lexer="python", theme="dracula"),
                title="Code to parse",
                expand=False,
            ),
            overflow="ellipsis",
        )
        ast_root = ast.parse(source)
        if not isinstance(ast_root, ast.Module):
            raise TypeError(
                f"'{name}' is not a module. AST analysis is only for modules."
            )
        if show_ast:
            self._console.print(
                Panel(
                    ast.dump(ast_root, indent=2, show_empty=True),
                    title=f"AST of {name}",
                    expand=False,
                ),
                overflow="ellipsis",
            )
        self._console.print("Analyzing callables...", style="green on black")
        self.visit(ast_root)
        return MitaineModule(
            root=name,
            classes=self._context["classes"],
            functions=self._context["functions"],
            methods=self._context["methods"],
            lambdas=self._context["lambdas"],
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self._context["classes"].append(MitaineClass(node.name, uuid1(), node))
        self._current_class.append(node)
        self._console.print(Pretty(node))
        self._console.print(f"{node.name}:", style="green on black")
        for el in node.body:
            self._console.print(f"\t|{el.name}", style="green on black")
        self.generic_visit(node)
        self._current_class.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        module_level = len(self._current_class) == 0
        color = "yellow" if module_level else "green"
        prefix = "module" if module_level else "class"
        self._console.print(Pretty(node))
        self._console.print(
            f"\[{prefix}] {node.name}: ({[arg.arg for arg in node.args.args]})",
            style=f"{color} on black",
        )
        mitaine_obj = MitaineFunction(node.name, uuid1(), node, [])
        if module_level:
            self._context["functions"].append(mitaine_obj)
        else:
            self._context["methods"][self._current_class[-1]].append(mitaine_obj)
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> Any:
        self._console.print(Pretty(node))
        self._console.print(
            f"{node}: ({[arg.arg for arg in node.args.args]})",
            style="green on black",
        )
        self._context["lambdas"].append(MitaineLambda(uuid1(), node, []))
        self.generic_visit(node)
