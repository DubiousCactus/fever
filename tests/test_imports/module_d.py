from typing import List


def function_d(name: str):
    print(f"Nothing to show here, {name}")


class TestClass:
    def __init__(self):
        self.callable = function_d
        self.child = self.NestedTestClass(self)

    def __call__(self):
        print(f"TestCase.__call__(); self.callable={self.callable}")
        self.callable("TestClass instance")

    def elaborate_function(self, arg1: str, arg2: List[bool]):
        print(f"Result of nested test: {self.child.nested_test(arg1)}")

    def hello(self, name: str):
        a = lambda x: x.upper()
        print(f"hello {a(name)}")

    class NestedTestClass:
        def __init__(self, owner):
            self.owner = owner

        def nested_test(self, name: str) -> int:
            self.owner.hello(name)
            return 1234
