import os

from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from ast_analysis import ASTAnalyzer
from import_hook import ImportHook


class NoPrint:
    def print(self, *args, **kwargs):
        pass


if __name__ == "__main__":
    console = Console() if bool(int(os.getenv("DEBUG", False))) else NoPrint()
    ihook = ImportHook(console)
    ihook.setup()

    print("Loading test module")
    import test

    print("Calling test.function()")
    test.function()

    # _ = input("Press a key to reload")
    # print("Reloading test module")
    # new_test = importlib.reload(test)
    # print("Calling test.function again")
    # new_test.function()

    print("AST analysis...")
    analyzer = ASTAnalyzer(console)
    for dep_name, dep_path, dep_module in ihook.get_dependencies("test"):
        mitaine_module = analyzer.analyze(dep_module, dep_name)
        console.print(Panel(Pretty(mitaine_module)))

    ihook.cleanup()
