#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2025-10-07 22:38:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.


import importlib
import sys
from typing import Dict

import networkx as nx
from rich.console import Console

from src import mitaine

from .ast_analysis import ASTAnalyzer, MitaineModule
from .dependency_tracker import DependencyTracker, ModuleLoadHook


class CallTracker(ModuleLoadHook):
    def __init__(self, console: Console):
        self._console = console
        self._dep_graph = nx.DiGraph()
        self._ast_analyzer = ASTAnalyzer(console)
        self._callables: Dict[str, MitaineModule] = {}

    def track(self, dependency_tracker: DependencyTracker):
        """
        Begin tracking function calls and building the runtime call graph.
        """
        dependency_tracker.register_module_load_hook(self)

    def on_module_load(self, module_name: str, code_str: str) -> None:
        if module_name == "mitaine":
            # TODO: Find a better way? But in fact, our import hook already excludes
            # non-user code, so this problem arises only when testing mitaine from
            # mitaine's project!
            return
        self._console.print(
            f"Analyzing AST for module '{module_name}'", style="blue on black"
        )
        module = sys.modules[module_name]
        self._callables[module_name] = self._ast_analyzer.analyze(
            module_name, module, show_ast=False
        )
        #
        # # TODO: For each callable in the returned MitaineModule, wrap it in the tracker
        # # decorator.
        # # Let's start with module level functions!
        for func in self._callables[module_name].functions:
            assert isinstance(func.obj, object)
            setattr(module, func.name, mitaine.track_calls(func.obj))
            sys.modules[module_name] = importlib.reload(module)
