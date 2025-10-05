import test_module_a


def other_function(from_module: str):
    print(f"called from {from_module}")
    test_module_a.other_function()
    # print("new statement!")
