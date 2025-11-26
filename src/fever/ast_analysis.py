#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-05 16:48:18 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

import ast
import inspect
from collections import defaultdict, deque
from typing import Any, Optional

from rich.panel import Panel
from rich.pretty import Pretty
from rich.syntax import Syntax

from .types import (
    FeverClass,
    FeverFunction,
    FeverGlobalVar,
    FeverImport,
    FeverLambda,
    FeverModule,
)
from .utils import ConsoleInterface


class GenericClass:
    pass


def generic_function():
    pass


class ASTAnalyzer(ast.NodeVisitor):
    def __init__(self, console: ConsoleInterface):
        self._console = console
        self._context_stack = deque()
        self._source: Optional[str] = None
        self._context = {}

    def _reset_context(self):
        self._context_stack = deque()
        self._source = None
        self._context = {
            "classes": [],
            "functions": [],
            "lambdas": [],
            "methods": defaultdict(list),
            "imports": [],
            "globals": [],
        }

    def make_module_inventory(
        self,
        name: str,
        module_obj: object,
        source_path: Optional[str] = None,
        show_ast=False,
    ) -> FeverModule:
        """
        Analyze the AST of a given object (typically a module, but possibly a class or
        other) and return a feverModule which tracks module-level functions, classes,
        lambdas and methods.
        """
        self._reset_context()
        if source_path:
            with open(source_path, "r") as f:
                self._source = f.read()
        else:
            self._source = inspect.getsource(module_obj)  # type: ignore
        self._context_stack.append(module_obj)
        self._console.print(
            Panel(
                Syntax(self._source, lexer="python", theme="dracula"),
                title="Code to parse",
                expand=False,
            ),
            overflow="ellipsis",
        )
        ast_root = ast.parse(self._source)
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
        return FeverModule(
            name=name,
            obj=module_obj,
            classes=self._context["classes"],
            functions=self._context["functions"],
            methods=self._context["methods"],
            lambdas=self._context["lambdas"],
            imports=self._context["imports"],
            globals=self._context["globals"],
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        class_obj = getattr(self._context_stack[-1], node.name, GenericClass)
        assert self._source is not None
        code = ast.get_source_segment(self._source, node)
        if code is None:
            raise RuntimeError(
                f"Could not retrieve source code for class '{node.name}'"
            )
        code_hash = hash(code)
        self._context_stack.append(class_obj)
        self._context["classes"].append(
            FeverClass(
                node.name,
                class_obj,
                code_hash,
                code,
            )
        )
        self._console.print(Pretty(node))
        self._console.print(f"{node.name}:", style="green on black")
        for el in node.body:
            self._console.print(
                f"\t|{getattr(el, 'name', 'unknown')}", style="green on black"
            )
        self.generic_visit(node)
        self._context_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        module_level = not inspect.isclass(self._context_stack[-1])
        color = "yellow" if module_level else "green"
        prefix = "module" if module_level else "class"
        self._console.print(
            f"\\[{prefix}] {node.name}: (args={[arg.arg for arg in node.args.args]})",
            style=f"{color} on black",
        )
        if inspect.isfunction(self._context_stack[-1]):
            # NOTE: Nested functions aren't defined on their own, they are part of their
            # parent's code object. So there's no need to track them, since they are
            # local and cannot be called from outside the parent function anyway. For
            # this reason, we just ignore them.
            self._context_stack.append(generic_function)
        else:
            # NOTE: If the function def isn't in the module object (ie this is a new
            # definition since the first module import), we use a generic and
            # will later compile the function into the registry, and then hook it into
            # the module. This requires no module reloading at all :)
            func_obj = getattr(self._context_stack[-1], node.name, generic_function)
            self._context_stack.append(func_obj)
            assert self._source is not None
            code = ast.get_source_segment(self._source, node)
            if code is None:
                raise RuntimeError(
                    f"Could not retrieve source code for func '{node.name}'"
                )
            code_hash = hash(code)
            fever_obj = FeverFunction(node.name, [], func_obj, code_hash, code)
            if module_level:
                self._context["functions"].append(fever_obj)
            else:
                self._context["methods"][self._context["classes"][-1]].append(fever_obj)
        self.generic_visit(node)
        self._context_stack.pop()

    def visit_Lambda(self, node: ast.Lambda) -> Any:
        self._console.print(
            f"{node}: (args={[arg.arg for arg in node.args.args]})",
            style="green on black",
        )
        # TODO: Figure out some trick to map lambdas? I know I was able to find lambdas
        # at crash time, in the stack trace. But we can't do it proactively ahead of
        # crash time due to their anonymous nature.
        func_obj = {}
        # TODO: Maybe we can't get their code object ahead of time, but we can at least
        # collect their arguments, which we could also track. We need to do this for all
        # callables proably.
        self._context["lambdas"].append(FeverLambda([], func_obj))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> Any:
        self._console.print(
            f"{node}: (names={[alias.name for alias in node.names]}, aliases={[alias.asname for alias in node.names]})",
        )
        assert self._source is not None
        code = ast.get_source_segment(self._source, node)
        if code is None:
            raise RuntimeError(
                f"Could not retrieve source code for imports '{node.names}'"
            )
        for alias in node.names:
            self._context["imports"].append(
                FeverImport(alias.name, code, alias.asname, sub_imports=None)
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        self._console.print(
            f"{node}: (names={[alias.name for alias in node.names]}, aliases={[alias.asname for alias in node.names]}, module={node.module})",
        )
        assert self._source is not None
        code = ast.get_source_segment(self._source, node)
        if code is None:
            raise RuntimeError(
                f"Could not retrieve source code for imports '{node.names}'"
            )
        if node.module is None:
            raise NotImplementedError(
                "Relative imports without module name are not supported."
            )
        self._context["imports"].append(
            FeverImport(
                node.module,
                code,
                sub_imports=[alias.name for alias in node.names],
            )
        )

    def visit_Assign(self, node: ast.Assign) -> Any:
        if "value" in node.value._fields and "id" in node.targets[0]._fields:
            target = node.targets[0].__dict__["id"]
            value = node.value.__dict__["value"]
            self._console.print(
                f"GlobalVar: (target={target}, value={value})",
            )
            self._context["globals"].append(FeverGlobalVar(target, value))
        self.generic_visit(node)
