import importlib
import os
import sys
from copy import copy, deepcopy
from types import ModuleType
from typing import Optional
from uuid import UUID

from rich.console import Console

import fever.registry as registry
from fever.ast_analysis import ASTAnalyzer, FeverModule, generic_function
from fever.registry import Registry

from .call_tracker import CallTracker
from .dependency_tracker import DependencyTracker
from .utils import ConsoleInterface


def parse_verbosity() -> int:
    v = os.getenv("VERBOSITY", "").lower()
    if v in ("v", "1"):
        return 1
    elif v in ("vv", "2"):
        return 2
    elif v in ("vvv", "3"):
        return 3
    return 0


class Fever:
    def __init__(self, rich_console: Optional[Console] = None):
        self._verbosity = parse_verbosity()
        console = None if self._verbosity == 0 else (rich_console or Console())
        self._console_if = ConsoleInterface(console)
        self._ast_analyzer = ASTAnalyzer(
            self._console_if if self._verbosity >= 3 else ConsoleInterface(None)
        )
        self.registry = Registry(
            self._ast_analyzer,
            self._console_if if self._verbosity >= 1 else ConsoleInterface(None),
            self,
        )
        self.dependency_tracker = DependencyTracker(
            self._console_if if self._verbosity >= 2 else ConsoleInterface(None),
            self,
        )
        self.call_tracker = CallTracker(
            self.registry,
            self._console_if if self._verbosity >= 2 else ConsoleInterface(None),
        )

    def setup(self):
        """
        Start tracking user imports and function/method calls in real time. Any `import`
        statements coming before calling this function will not be tracked, and as a
        result, any function calls to functions/classes defined in those modules will not be
        tracked.


        Fever tracks imports and wraps all callables to insert a registry hook, where
        the actual code will be stored and updated. It does so in the following steps:
        1. Insert an import hook which detects user modules and ignores others.
        2. On first import, load the module from disk via exec(); this compiles it to byte code.
        3. Retrieve the compiled module from sys.modules.
        4. Analyze its AST to find all callables.
        4. Wrap each callable in a decorator and save the underlying pointer to a registry.
        5. Replace the module's function pointer with our wrapped function pointer. Any
        subsequent call to the callable will be redirected to the proxy callable which
        will pull the bytecode from the registry.
        """
        self.dependency_tracker.setup(show_skips=self._verbosity == 3)

    def cleanup(self):
        """
        Remove the import hook.
        """
        self.dependency_tracker.cleanup()
        self.registry.cleanup()

    def on_module_load(self, module_name: str, code_str: str) -> None:
        self.registry.on_module_load(module_name, code_str)

    def on_new_import(self, module_name: str, module: object) -> None:
        pass

    def plot_dependency_graph(self):
        self.dependency_tracker.plot()

    def plot_call_graph(self):
        self.call_tracker.plot()

    def on_registry_add(self, module: FeverModule) -> None:
        # FIXME: Currently, we re-wrap every callable whenever this method is called!
        # This is wrong, because we check whether func.obj is wrapped, but func.obj is
        # never updated since we take the wrapper and replace the pointer in the module
        # object. ie func.obj is always the original object! We need to re-implement the
        # wrapping logic and simplify it. But let's first pass all tests.
        for func in module.functions:
            # assert not hasattr(getattr(module.obj, func.name), "__wrapped__"), (
            #     f"Function {func.name} was already wrapped! This is not supposed to happen."
            # )
            assert isinstance(func.obj, object)
            assert func.obj is not generic_function, (
                f"on_registry_add(): function {func.name} is the generic function!"
            )
            if func.name not in self.registry._FUNCTION_DEFS[module.root]:
                self.registry._FUNCTION_DEFS[module.root][func.name] = func.obj
            if not hasattr(func.obj, "__wrapped__"):
                setattr(module.obj, func.name, self.call_tracker.track_calls(func.obj))
            # FIXME: This invalidates the original func.obj right? I mean we won't be
            # using it, so should we update it?

        for class_ in module.classes:
            assert isinstance(class_, object)
            if not hasattr(module.obj, class_.name):
                setattr(module.obj, class_.name, class_.obj)
            if class_.name not in self.registry._CLASS_DEFS[module.root]:
                self.registry._CLASS_DEFS[module.root][class_.name] = class_.obj
                setattr(module.obj, class_.name, class_.obj)

        for class_, methods in module.methods.items():
            assert isinstance(class_, object)
            for method in methods:
                # FIXME: Nested classes can't be asserted this way
                # class_obj = getattr(module.obj, class_.name, None)
                # assert not hasattr(getattr(class_obj, method.name), "__wrapped__"), (
                #     f"Function {method.name} was already wrapped! This is not supposed to happen."
                # )
                assert isinstance(method.obj, object)
                assert method.obj is not generic_function, (
                    f"on_registry_add(): method {method.name} is the generic function!"
                )
                if class_.name not in self.registry._CLASS_METHOD_DEFS[module.root]:
                    self.registry._CLASS_METHOD_DEFS[module.root][class_.name] = {
                        method.name: method.obj
                    }
                elif (
                    method.name
                    not in self.registry._CLASS_METHOD_DEFS[module.root][class_.name]
                ):
                    self.registry._CLASS_METHOD_DEFS[module.root][class_.name][
                        method.name
                    ] = method.obj
                if not hasattr(method.obj, "__wrapped__"):
                    setattr(
                        class_.obj,
                        method.name,
                        self.call_tracker.track_calls(method.obj, fever_class=class_),
                    )
        for lambda_ in module.lambdas:
            # NOTE: We can't really track lambdas as they are anonymous and we have no
            # way to hook them unless we do some AST rewriting?. But I have been able to
            # track lambdas *reactively* at crash time, so I may adopt this strategy
            # later.
            pass

    def reload(self):
        """
        Reload all callables that have changed on disk by comparing their hash to the
        ones stored in the registry. All callables are automatically tracked based on
        imports and function calls that happen after calling `setup()`.

        For each tracked module:
          1. Reload from disk.
          2. Run AST analysis to extract callables (functions and methods).
          3. Compare hashes of callables with those in the registry.
          4. For each hash mismatch:
              a. Replace the function bytecode in the registry.
          5. For each new callable not found in registry, add it.
        """
        console = self._console_if if self._verbosity >= 1 else ConsoleInterface(None)
        for module_name in self.dependency_tracker.all_imports:
            console.print(f"Inspecting module '{module_name}'", style="purple on black")
            if module_name not in sys.modules:
                console.print(
                    f"Module '{module_name}' not found in sys.modules, skipping.",
                    style="red on black",
                )
                continue
            module_obj: ModuleType = sys.modules[module_name]
            # NOTE: set module_obj = None to re-execute the module code. This way we can
            # handle new definitions (new functions/classes) that were not present before.
            # FIXME: Yeah for now I'm returning an empty code object for new functions,
            # which should work fine. But it will break for new classes because we won't
            # be able to find class methods. Although do we need to? No, let's try with
            # generic objects for placeholder.
            cmp_fever_module: FeverModule = self._ast_analyzer.analyze(
                module_name,
                module_obj=module_obj,
                source_path=getattr(module_obj, "__file__"),
            )
            for cmp_func in cmp_fever_module.functions:
                # NOTE: Now cames the tricky part... How do we match our previously parsed
                # functions to the new parsed functions?
                # Option 1: by hash(name + scope + args)
                # Option 2: by other heuristics with a diff algorithm?
                # We'll use option 1 for now.
                if fever_callable := self.registry.find_function_by_name(
                    cmp_func.name, module_name
                ):
                    if fever_callable.hash != cmp_func.hash:
                        console.print(
                            f"Hash mismatch for function '{fever_callable.name}': hot reloading!",
                            style="green on black",
                        )
                        # WARN: cmp_func.obj is not valid! Because we get it from
                        # the original module, and it was not reloaded. So either we
                        # reload the module, but I don't like it because it replaces
                        # sys.modules and reloads the entire thing, or we exec
                        # function code only!
                        # INFO: Compile the new function code into the registry
                        # namespace, where it should already be defined since the
                        # original function is placed there by our call wrapper. For
                        # subsequent calls to the function, from anywhere, the new code
                        # will be used automatically. It's beautiful, there is no need
                        # to refresh imports or references.
                        # FIXME: This assert is broken. We need the hierarchy of the
                        # function definition. It will only work for level 0 (module).
                        # assert hasattr(
                        #     module_namespace[fever_callable.name], "__wrapped__"
                        # ), (
                        #     f"Function '{fever_callable.name}' was never wrapped "
                        #     + "and so is not in the registry. "
                        #     + "This should not happen, please make a bug report."
                        # )
                        # NOTE: Here we need to put the module namespace into
                        # the registry namespace so that exec() can access the globals
                        # during execution. This seems like the most robust solution
                        # right now, but I will think about it again and implement loads
                        # of tests.
                        registry_namespace = self.registry._FUNCTION_DEFS[module_name]
                        module_namespace = vars(module_obj)
                        for k, v in module_namespace.items():
                            if k in registry_namespace:
                                continue
                            registry_namespace[k] = v
                        exec(cmp_func.code, registry_namespace)
                else:
                    # INFO: The function doesn't exist in the loaded module, but we have
                    # the source code from AST analysis of the updated source file.
                    # Instead of reloading the entire module, we can just compile the
                    # function in the registry namespace, and then hook it into the
                    # module (done in the call tracker, called by registry.add_function()).
                    registry_namespace = self.registry._FUNCTION_DEFS[module_name]
                    module_namespace = vars(module_obj)
                    for k, v in module_namespace.items():
                        if k in registry_namespace:
                            continue
                        registry_namespace[k] = v
                    exec(cmp_func.code, registry_namespace)
                    cmp_func.obj = registry_namespace[cmp_func.name]
                    self.registry.add_function(module_name, cmp_func)

            for cmp_class, cmp_methods in cmp_fever_module.methods.items():
                for cmp_method in cmp_methods:
                    if fever_callable := self.registry.find_method_by_name(
                        cmp_method.name, cmp_class.name, module_name
                    ):
                        if fever_callable.hash != cmp_method.hash:
                            console.print(
                                f"Hash mismatch for method '{fever_callable.name}': hot reloading!",
                                style="green on black",
                            )
                            # FIXME: This assert is broken. We need the hierarchy of the
                            # method definition. It will only work for level 1 (class in
                            # module).
                            # assert hasattr(
                            #     getattr(
                            #         module_namespace[cmp_class.name],
                            #         fever_callable.name,
                            #     ),
                            #     "__wrapped__",
                            # ), (
                            #     f"Function '{fever_callable.name}' was never wrapped "
                            #     + "and so is not in the registry. "
                            #     + "This should not happen, please make a bug report."
                            # )
                            module_namespace = vars(module_obj)
                            registry_namespace = self.registry._CLASS_METHOD_DEFS[
                                module_name
                            ][cmp_class.name]
                            for k, v in module_namespace.items():
                                if k in registry_namespace:
                                    continue
                                registry_namespace[k] = v
                            exec(cmp_method.code, registry_namespace)
                    else:
                        module_namespace = vars(module_obj)
                        if cmp_class.name not in self.registry._CLASS_DEFS[module_name]:
                            registry_namespace = self.registry._CLASS_DEFS[module_name]
                            for k, v in module_namespace.items():
                                if k in registry_namespace:
                                    continue
                                registry_namespace[k] = v
                            exec(cmp_class.code, registry_namespace)
                            cmp_class.obj = registry_namespace[cmp_class.name]
                            self.registry._CLASS_METHOD_DEFS[module_name][
                                cmp_class.name
                            ] = {}
                            self.registry.add_class(module_name, cmp_class)
                        registry_namespace = self.registry._CLASS_METHOD_DEFS[
                            module_name
                        ][cmp_class.name]
                        # FIXME: This is such a mess. Can we execute the code in an
                        # isolated namespace, and then move the compiled function *only*
                        # to the target namespace? Or would that break pointers in the
                        # byte code?
                        for k, v in module_namespace.items():
                            if k in registry_namespace:
                                continue
                            registry_namespace[k] = v
                        exec(cmp_method.code, registry_namespace)
                        cmp_method.obj = registry_namespace[cmp_method.name]
                        if class_ := self.registry.find_class_by_name(
                            cmp_class.name, module_name
                        ):
                            self.registry.add_method(module_name, class_, cmp_method)
                        else:
                            raise RuntimeError(
                                f"Class '{cmp_class.name}' not found in registry "
                            )

    def rerun(self, entry_point: UUID):
        """
        Rerun the entire call graph from given entry point (callable UUID), but use
        cached results for every node in the graph that wasn't reloaded.
        """
        raise NotImplementedError
