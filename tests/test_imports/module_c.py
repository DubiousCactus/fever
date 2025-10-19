import module_a


def other_function(from_module: str) -> bool:
    print(f"called from {from_module}")
    module_a.second_function()
    print("new statement!")
    return True
