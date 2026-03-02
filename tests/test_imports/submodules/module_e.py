import numpy as np

def function_e():
    print("yo e")

def function_foreign_imports() -> np.ndarray:
    x = np.array([1, 2, 3])
    return x * 3


def nested_functions() -> int:
    def nested_a() -> str:
        def nested_b() -> int:
            return 123

        return f"nested_a calls modified nested_b: {nested_b()}"

    return len(nested_a())


class ClassE:
    def method_e(self):
        print("method_e called")
