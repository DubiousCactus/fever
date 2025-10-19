import random

from module_b import TestCase, module_level_func, other_module_level_func


def function() -> str:
    print("test.function()")
    test_module = TestCase()
    return test_module.elaborate_function("world", [False, False, False])


def function_deep_nested() -> str:
    print("test.function_deep_nested()")
    test_module = TestCase()
    test_module()
    return test_module.elaborate_function("world", [False, False, False])


def function_with_lambda_call() -> str:
    print("test.function_with_lambda_call()")
    test_module = TestCase()
    return test_module.elaborate_function("world", [True, False, True])


def second_function():
    print("im an other function")
    for _ in range(random.randint(3, 7)):
        module_level_func("second_function")
    other_module_level_func("ya")
