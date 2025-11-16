import os
import sys
import warnings
from types import FrameType, ModuleType
from typing import Callable, Dict, Optional
from uuid import UUID

from rich.console import Console

from fever.ast_analysis import (
    ASTAnalyzer,
    FeverClass,
    FeverFunction,
    FeverModule,
    generic_function,
)
from fever.registry import Registry

from .call_tracker import CallTracker
from .dependency_tracker import DependencyTracker
from .utils import ConsoleInterface, FeverWarning


def compile_code_in_namespace(
    code: str, callable_name: str, module_namespace: Dict, registry_namespace: Dict
) -> None:
    """
    Execute the given code string in the provided registry namespace, such that the
    function/class/method object pointer is stored in the registry. To do this, we copy
    the module namespace and the registry namespace in a temporary namespace so that
    exec() can access the globals during execution. We then update the registry
    namespace with the new code definition. This seems like the most robust solution
    right now, but I will think about it again and implement loads of tests.
    """
    exec_namespace = module_namespace | registry_namespace
    exec(code, exec_namespace)
    registry_namespace.update(
        {
            k: v
            for k, v in exec_namespace.items()
            if k in registry_namespace or k == callable_name
        }
    )


def parse_verbosity() -> int:
    v = os.getenv("VERBOSITY", "").lower()
    if v in ("v", "1"):
        return 1
    elif v in ("vv", "2"):
        return 2
    elif v in ("vvv", "3"):
        return 3
    elif v in ("vvvv", "4"):
        return 4
    return 0


class FeverCore:
    def __init__(self, rich_console: Optional[Console] = None):
        self._verbosity = parse_verbosity()
        console = None if self._verbosity == 0 else (rich_console or Console())
        self._console_if: ConsoleInterface = ConsoleInterface(console)
        self._ast_analyzer: ASTAnalyzer = ASTAnalyzer(
            self._console_if if self._verbosity >= 3 else ConsoleInterface(None)
        )
        self.registry: Registry = Registry()
        self.dependency_tracker: DependencyTracker = DependencyTracker(
            self._console_if if self._verbosity >= 2 else ConsoleInterface(None),
            self.on_module_load,
        )
        self._call_tracker: CallTracker = CallTracker(
            self.registry,
            self._console_if if self._verbosity >= 2 else ConsoleInterface(None),
        )

    def setup(self, caller_frame: Optional[FrameType] = None):
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
        self.dependency_tracker.setup(
            show_skips=self._verbosity == 4,
            caller_frame=caller_frame or sys._getframe(1),
        )

    def cleanup(self):
        """
        Remove the import hook.
        """
        self.dependency_tracker.cleanup()
        self.registry.cleanup()

    def on_module_load(self, module_name: str) -> None:
        """
        Make the inventory of all callables (functions, classes, methods) defined in the
        imported module 'module_name', register their code in the registry, and track
        their calls.
        """
        if (module := sys.modules.get(module_name)) is None:
            raise RuntimeError(f"Module '{module_name}' not found in sys.modules")
        else:
            self._console_if.print(
                f"Analyzing AST for module '{module_name}'", style="blue on black"
            )
            fever_module = self._ast_analyzer.make_module_inventory(
                module_name, module, show_ast=False
            )
            assert fever_module.obj == module
            self.registry.add_module(module_name, fever_module)
            self._track_module(fever_module)

    def on_new_import(self, module_name: str, module: object) -> None:
        _ = module_name
        _ = module

    def plot_dependency_graph(self):
        self.dependency_tracker.plot()

    def plot_call_graph(self):
        self._call_tracker.plot()

    def _track_module(self, module: FeverModule) -> None:
        for func in module.functions:
            self._track_function(func, module)

        for class_ in module.classes:
            assert isinstance(class_, object)
            self._track_class(class_, module)

        for class_, methods in module.methods.items():
            assert isinstance(class_, object)
            for method in methods:
                self._track_method(method, class_, module)

        # NOTE: We can't really track lambdas as they are anonymous and we have no
        # way to hook them unless we do some AST rewriting?. But I have been able to
        # track lambdas *reactively* at crash time, so I may adopt this strategy
        # later.

    def _track_function(self, func: FeverFunction, module: FeverModule) -> None:
        if hasattr(getattr(module.obj, func.name, {}), "__wrapped__"):
            warnings.warn(
                f"Function {func.name} was already wrapped! This is not supposed to happen.",
                FeverWarning,
            )
        assert isinstance(func.obj, object)
        assert func.obj is not generic_function, (
            f"on_registry_add(): function {func.name} is the generic function!"
        )
        if not isinstance(func.obj, Callable):
            warnings.warn(
                f"Function {func.name} is not a callable! Tracking of '{func.obj.__class__}' is currently not implemented.",
                FeverWarning,
            )
            return
        setattr(module.obj, func.name, self._call_tracker.track_calls(func, module))

    def _track_method(
        self, method: FeverFunction, class_: FeverClass, module: FeverModule
    ) -> None:
        # FIXME: Nested classes can't be asserted this way
        class_obj = getattr(module.obj, class_.name, {})
        if hasattr(getattr(class_obj, method.name, {}), "__wrapped__"):
            warnings.warn(
                f"Function {method.name} was already wrapped! This is not supposed to happen.",
                FeverWarning,
            )
        assert isinstance(method.obj, object)
        if not isinstance(method.obj, Callable):
            warnings.warn(
                f"Method {method.name} is not a callable! Tracking of '{method.obj.__class__}' is currently not implemented.",
                FeverWarning,
            )
            return
        assert method.obj is not generic_function, (
            f"on_registry_add(): method {method.name} is the generic function!"
        )
        setattr(
            class_.obj,
            method.name,
            self._call_tracker.track_calls(method, module, class_),
        )

    def _track_class(self, class_: FeverClass, module: FeverModule) -> None:
        # INFO: No tracking is done for the class itself, only for its methods. But in
        # the case where a new class is defined during reloading, we need to insert it
        # into the existing module object.
        setattr(module.obj, class_.name, class_.obj)

    def reload(self, module_list: Optional[list[str]] = None) -> None:
        """
        Reload all callables that have changed on disk by comparing their hash to the
        ones stored in the registry. All callables are automatically tracked based on
        imports and function calls that happen after calling `setup()`.

        For each tracked module:
          1. Reload from disk.
          2. Run AST analysis to make module inventory (functions, classes, methods).
          3. Compare hashes of callables with those in the registry.
          4. For each hash mismatch:
              a. Replace the function bytecode in the registry.
          5. For each new callable not found in registry, add it.
        """
        for module_name in self.dependency_tracker.all_imports:
            if module_list is not None and module_name not in module_list:
                continue
            self._console_if.print(
                f"Inspecting module '{module_name}'", style="purple on black"
            )
            if module_name not in sys.modules:
                self._console_if.print(
                    f"Module '{module_name}' not found in sys.modules, skipping.",
                    style="red on black",
                )
                continue
            module_obj: ModuleType = sys.modules[module_name]
            module_namespace = vars(module_obj)
            cmp_fever_module: FeverModule = self._ast_analyzer.make_module_inventory(
                module_name,
                module_obj=module_obj,
                source_path=getattr(module_obj, "__file__"),
            )
            # WARN: The new code object returned by AST analysis is stale because we get
            # it from the original module. Instead of reloading the entire module, we
            # recompile the callable.
            # INFO: We compile the new function code into the registry namespace, where
            # it should already be defined since the original function is placed there
            # by our call wrapper. Subsequent calls to the function will point to the
            # updated code in the reigstry. It's beautiful, there is no need to refresh
            # imports or references.
            # WARN: Make sure to start with new imports, so that new functions that
            # depend on them will compile.
            self._handle_new_imports(module_name, module_namespace, cmp_fever_module)
            self._reload_functions(module_name, module_namespace, cmp_fever_module)
            self._reload_classes_and_methods(
                module_name, module_namespace, cmp_fever_module
            )

    def _reload_functions(
        self, module_name: str, module_namespace: Dict, fever_module: FeverModule
    ) -> None:
        func_registry_namespace = self.registry._FUNCTION_PTRS[module_name]
        for cmp_func in fever_module.functions:
            assert cmp_func.code is not None
            if (
                fever_callable := self.registry.find_function_by_name(
                    cmp_func.name, module_name
                )
            ) and fever_callable.hash != cmp_func.hash:
                self._console_if.print(
                    f"Hash mismatch for function '{fever_callable.name}': hot reloading!",
                    style="green on black",
                )
                compile_code_in_namespace(
                    cmp_func.code,
                    cmp_func.name,
                    module_namespace,
                    func_registry_namespace,
                )
                fever_callable.hash = cmp_func.hash
            elif not fever_callable:
                # INFO: The function doesn't exist in the loaded module so we
                # compile it and track it.
                compile_code_in_namespace(
                    cmp_func.code,
                    cmp_func.name,
                    module_namespace,
                    func_registry_namespace,
                )
                cmp_func.obj = func_registry_namespace[cmp_func.name]
                self.registry.add_function(module_name, cmp_func)
                self._track_function(cmp_func, fever_module)

    def _reload_classes_and_methods(
        self, module_name: str, module_namespace: Dict, fever_module: FeverModule
    ) -> None:
        for cmp_class, cmp_methods in fever_module.methods.items():
            class_registry_namespace = self.registry._CLASS_PTRS[module_name]
            assert cmp_class.code is not None
            if cmp_class.name not in class_registry_namespace:
                # INFO: The class doesn't exist in the loaded module so we
                # compile it and track it.
                compile_code_in_namespace(
                    cmp_class.code,
                    cmp_class.name,
                    module_namespace,
                    class_registry_namespace,
                )
                cmp_class.obj = class_registry_namespace[cmp_class.name]
                self.registry.add_class(module_name, cmp_class)
                self._track_class(cmp_class, fever_module)

            method_registry_namespace = self.registry._CLASS_METHOD_PTRS[module_name][
                cmp_class.name
            ]
            for cmp_method in cmp_methods:
                assert cmp_method.code is not None
                if (
                    fever_callable := self.registry.find_method_by_name(
                        cmp_method.name, cmp_class.name, module_name
                    )
                ) and fever_callable.hash != cmp_method.hash:
                    self._console_if.print(
                        f"Hash mismatch for method '{fever_callable.name}': hot reloading!",
                        style="green on black",
                    )
                    compile_code_in_namespace(
                        cmp_method.code,
                        cmp_method.name,
                        module_namespace,
                        method_registry_namespace,
                    )
                    fever_callable.hash = cmp_method.hash
                elif not fever_callable:
                    # INFO: The method doesn't exist in the loaded module so we
                    # compile it and track it.
                    compile_code_in_namespace(
                        cmp_method.code,
                        cmp_method.name,
                        module_namespace,
                        method_registry_namespace,
                    )
                    cmp_method.obj = method_registry_namespace[cmp_method.name]
                    if class_ := self.registry.find_class_by_name(
                        cmp_class.name, module_name
                    ):
                        self.registry.add_method(module_name, class_, cmp_method)
                        self._track_method(cmp_method, class_, fever_module)
                    else:
                        raise RuntimeError(
                            f"Class '{cmp_class.name}' not found in registry. "
                            + "This should never happen, please make a bug report."
                        )

    def _handle_new_imports(
        self,
        module_name: str,
        module_namespace: Dict,
        fever_module: FeverModule,
    ) -> None:
        # INFO: New imports need to be executed and placed in the module namespace so that new
        # functions that depend on them can be compiled correctly. No need to modify the
        # registry here.
        for cmp_import in fever_module.imports:
            if (
                self.registry.find_import_by_name_or_alias(
                    cmp_import.module, module_name
                )
                is None
            ):
                self._console_if.print(
                    f"'New import detected: '{cmp_import.module}'"
                    + f" (with sub-imports: {cmp_import.sub_imports})"
                    if cmp_import.sub_imports
                    else "",
                    style="green on black",
                )
                assert cmp_import.code is not None
                exec(cmp_import.code, module_namespace)

    def rerun(self, entry_point: UUID):
        """
        Rerun the entire call graph from given entry point (callable UUID), but use
        cached results for every node in the graph that wasn't reloaded.
        """
        _ = entry_point
        raise NotImplementedError
