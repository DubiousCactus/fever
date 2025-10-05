from typing import List

from other_test_module import other_function


def module_level_func(name: str):
    print(f"Hello, {name}!")


class TestCase:
    def __init__(self):
        self.callable = other_function
        self.child = self.NestedTestCase(self)

    def __call__(self):
        print(f"TestCase.__call__(); self.callable={self.callable}")
        self.callable("TestCase instance")

    def elaborate_function(self, arg1: str, arg2: List[bool]):
        self.child.nested_test(arg1)

    def hello(self, name: str):
        a = lambda x: x.upper()
        print(f"hello {a(name)}")

    class NestedTestCase:
        def __init__(self, owner):
            self.owner = owner

        def nested_test(self, name: str):
            self.owner.hello(name)


def other_module_level_func(name: str):
    print(f"Hello again, {name}!")
