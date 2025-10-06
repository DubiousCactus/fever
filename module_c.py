import module_a


def other_function(from_module: str):
    print(f"called from {from_module}")
    module_a.other_function()
    # print("new statement!")
