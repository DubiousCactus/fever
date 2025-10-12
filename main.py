import os

from fever import Fever

if __name__ == "__main__":
    viz = bool(int(os.getenv("VIZ", False)))
    fever = Fever()
    fever.setup()

    # Example 1:
    # print("Loading module_a")
    # import module_a
    #
    # print("Calling module_a.function()")
    # module_a.function()
    #
    # _ = input("Press a key to reload")
    # fever.reload()  # Only reloads callables that changed on disk
    # print("Calling module_a.function() on a fresh code base with maintained state:")
    # module_a.function()

    # Example 2:
    print("Loading module_a")
    import module_a

    print("Calling module_a.function()")
    module_a.function()

    if viz:
        fever.plot_dependency_graph()
        fever.plot_call_graph()

    _ = input("Press a key to reload and rerun")
    fever.reload()  # Only reloads callables that changed on disk
    module_a.function()
    # fever.rerun(
    #     entry_point="idk-yet-but-probably-find-UUID-from-func-name"
    # )  # Only re-executes reloaded code, but goes through the call graph from entry point

    fever.cleanup()
