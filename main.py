import os

from fever import Fever

if __name__ == "__main__":
    viz = bool(int(os.getenv("VIZ", False)))
    fever = Fever()
    fever.setup()

    print("Loading module_a")
    import module_a

    print("Calling module_a.function()")
    module_a.function()

    # _ = input("Press a key to reload")
    # print("Reloading test module")
    # new_test = importlib.reload(test)
    # print("Calling test.function again")
    # new_test.function()

    if viz:
        fever.plot_dependency_graph()
        fever.plot_call_graph()

    fever.cleanup()
