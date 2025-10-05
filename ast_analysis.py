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

from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.syntax import Syntax


@dataclass
class MitaineModule:
    classes: List[ast.ClassDef]
    functions: List[ast.FunctionType]
    methods: Dict[ast.ClassDef, List[ast.FunctionType]]
    lambdas: List[ast.Lambda]


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

    def analyze(self, obj: object, name: str) -> MitaineModule:
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
            classes=self._context["classes"],
            functions=self._context["functions"],
            methods=self._context["methods"],
            lambdas=self._context["lambdas"],
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self._context["classes"].append(node)
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
        if module_level:
            self._context["functions"].append(node)
        else:
            self._context["methods"][self._current_class[-1]].append(node)
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> Any:
        self._console.print(Pretty(node))
        self._console.print(
            f"{node}: ({[arg.arg for arg in node.args.args]})",
            style="green on black",
        )
        self._context["lambdas"].append(node)
        self.generic_visit(node)
