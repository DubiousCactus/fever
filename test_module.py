from other_test_module import other_function


class TestCase:
    def __init__(self):
        self.callable = other_function

    def __call__(self):
        print(f"TestCase.__call__(); self.callable={self.callable}")
        self.callable("TestCase instance")
