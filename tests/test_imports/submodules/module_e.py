def function_e():
    print("yo e")


def nested_functions() -> int:
    def nested_a() -> str:
        def nested_b() -> int:
            return 123

        return f"nested_a calls nested_b: {nested_b()}"

    return len(nested_a())


class ClassE:
    def method_e(self):
        print("method_e called")
