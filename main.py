import os

from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from ast_analysis import ASTAnalyzer
from dependency_tracker import DependencyTracker


class NoPrint:
    def print(self, *args, **kwargs):
        pass


if __name__ == "__main__":
    console = Console() if bool(int(os.getenv("DEBUG", False))) else NoPrint()
    dep_tracker = DependencyTracker(console)
    dep_tracker.setup(show_skips=False)

    print("Loading test module")
    import test

    print("Calling test.function()")
    test.function()

    # _ = input("Press a key to reload")
    # print("Reloading test module")
    # new_test = importlib.reload(test)
    # print("Calling test.function again")
    # new_test.function()

    dep_tracker.plot_dependency_graph()
    print("AST analysis...")
    analyzer = ASTAnalyzer(console)
    for dep_name, dep_path, dep_module in dep_tracker.get_dependencies("test"):
        mitaine_module = analyzer.analyze(dep_module, dep_name, show_ast=False)
        console.print(Panel(Pretty(mitaine_module)))

    dep_tracker.cleanup()
