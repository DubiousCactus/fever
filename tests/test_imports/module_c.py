import module_a


def other_function(from_module: str) -> bool:
    print(f"called from {from_module}")
    module_a.second_function()
    print("new statement!")
    return True


class TestClass:
    def call_me_baby(self):
        return "Hey, I just met you!"
def new_function() -> str:
    return "I think therefore I am"
