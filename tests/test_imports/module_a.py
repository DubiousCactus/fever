import random

from module_b import TestCase, module_level_func, other_module_level_func


def function() -> str:
    print("test.function()")
    test_module = TestCase()
    return test_module.elaborate_function("earth", [False, False, False])


def function_deep_nested() -> str:
    print("test.function_deep_nested()")
    test_module = TestCase()
    test_module()
    return test_module.elaborate_function("earth", [False, False, False])


def function_with_lambda_call() -> str:
    print("test.function_with_lambda_call()")
    test_module = TestCase()
    return test_module.elaborate_function("earth", [True, False, True])


def second_function():
    print("im an other function")
    for _ in range(random.randint(3, 7)):
        module_level_func("second_function")
    other_module_level_func("ya")


global_var_a = 10
global_var_b = 20

def function_with_globals() -> int:
    return global_var_a + global_var_b


import numpy as np

def function_with_numpy() -> np.ndarray:
    a = np.array([4, 5, 6])
    return a + 1


from numpy import array

def function_with_numpy_array() -> array:
    a = array([7, 8, 9])
    return a + 2


def new_fn_a():
    return 123

def new_fn_b():
    return new_fn_a()+1