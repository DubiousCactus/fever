from typing import List

from module_c import other_function


def module_level_func(name: str):
    print(f"Hello, {name}!")
    other_module_level_func("yo")


class TestCase:
    def __init__(self):
        self.callable = other_function
        self.child = self.NestedTestCase(self)

    def __call__(self):
        print(f"TestCase.__call__(); self.callable={self.callable}")
        self.callable("TestCase instance")

    def elaborate_function(self, arg1: str, arg2: List[bool]) -> str:
        print(f"Result of nested test: {self.child.nested_test(arg1, arg2[0])}")
        return str(self.child.nested_test(arg1, arg2[0]))

    def hello(self, name: str):
        return f"hello {name}"

    def hello_upper(self, name: str):
        a = lambda x: x.upper()
        return f"hello {a(name)}"

    class NestedTestCase:
        def __init__(self, owner):
            self.owner = owner

        def nested_test(self, name: str, use_lambda: bool) -> str:
            return (
                self.owner.hello(name)
                if not use_lambda
                else self.owner.hello_upper(name)
            )


def other_module_level_func(name: str):
    print(f"Hello again, {name}!")
