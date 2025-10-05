from test_module_b import TestCase


def function():
    print("test.function()")
    test_module = TestCase()
    test_module()


def other_function():
    print("im an other function")
