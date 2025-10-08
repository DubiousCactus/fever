import os

from rich.console import Console
from rich.pretty import Pretty

import mitaine


class NoPrint:
    def print(self, *args, **kwargs):
        pass


if __name__ == "__main__":
    console = Console() if bool(int(os.getenv("DEBUG", False))) else NoPrint()
    dep_tracker = mitaine.DependencyTracker(console)
    dep_tracker.setup(show_skips=False)
    call_tracker = mitaine.CallTracker(console)
    call_tracker.track(dep_tracker)

    print("Loading module_a")
    import module_a

    print("Calling module_a.function()")
    module_a.function()
    # module_a.function()
    # module_a.function()
    # module_a.function()
    # module_a.function()
    # module_a.function()

    # _ = input("Press a key to reload")
    # print("Reloading test module")
    # new_test = importlib.reload(test)
    # print("Calling test.function again")
    # new_test.function()

    if bool(int(os.getenv("VIZ", False))):
        dep_tracker.plot_dependency_graph()
    console.print("Modules which depend on 'module_a':")
    console.print(Pretty(dep_tracker.get_dependencies("module_a")))
    console.print("Modules which depend on 'module_c':")
    console.print(Pretty(dep_tracker.get_dependencies("module_c")))
    # _ = ASTAnalyzer
    # _ = Pretty
    # _ = Panel
    # print("AST analysis...")
    # analyzer = ASTAnalyzer(console)
    # for dep_name, dep_path, dep_module in dep_tracker.get_dependent_modules(
    #     "module_c"
    # ):
    #     mitaine_module = analyzer.analyze(dep_module, dep_name, show_ast=False)
    #     console.print(Panel(Pretty(mitaine_module)))
    #     break

    dep_tracker.cleanup()
