# import fever
import random

from module_b import TestCase, module_level_func, other_module_level_func


# @fever.track_calls
def function():
    print("test.function()")
    test_module = TestCase()
    test_module()
    test_module.elaborate_function("world", [True, False, True])


def second_function():
    print("im an other function")
    for _ in range(random.randint(3, 7)):
        module_level_func("second_function")
    other_module_level_func("ya")
