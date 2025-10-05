import importlib

from import_hook import ImportHook

if __name__ == "__main__":
    ihook = ImportHook()
    ihook.setup()

    print("Loading test module")
    import test

    print("Calling test.function()")
    test.function()

    _ = input("Press a key to reload")
    print("Reloading test module")
    new_test = importlib.reload(test)
    print("Calling test.function again")
    new_test.function()

    ihook.cleanup()
