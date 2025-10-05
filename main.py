import os

from rich.console import Console
from rich.pretty import Pretty

from dependency_tracker import DependencyTrackerV2


class NoPrint:
    def print(self, *args, **kwargs):
        pass


if __name__ == "__main__":
    console = Console() if bool(int(os.getenv("DEBUG", False))) else NoPrint()
    dep_tracker = DependencyTrackerV2(console)
    dep_tracker.setup(show_skips=False)

    print("Loading test_module_a")
    import test_module_a

    print("Calling test_module_a.function()")
    test_module_a.function()

    # _ = input("Press a key to reload")
    # print("Reloading test module")
    # new_test = importlib.reload(test)
    # print("Calling test.function again")
    # new_test.function()

    if bool(int(os.getenv("VIZ", False))):
        dep_tracker.plot_dependency_graph()
    console.print("Modules which depend on 'test_module_a':")
    console.print(Pretty(dep_tracker.get_dependencies("test_module_a")))
    console.print("Modules which depend on 'test_module_c':")
    console.print(Pretty(dep_tracker.get_dependencies("test_module_c")))
    # _ = ASTAnalyzer
    # _ = Pretty
    # _ = Panel
    # print("AST analysis...")
    # analyzer = ASTAnalyzer(console)
    # for dep_name, dep_path, dep_module in dep_tracker.get_dependent_modules(
    #     "test_module_c"
    # ):
    #     mitaine_module = analyzer.analyze(dep_module, dep_name, show_ast=False)
    #     console.print(Panel(Pretty(mitaine_module)))
    #     break

    dep_tracker.cleanup()
