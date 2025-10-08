# import mitaine
from module_b import TestCase


# @mitaine.track_calls
def function():
    print("test.function()")
    test_module = TestCase()
    test_module()


def second_function():
    print("im an other function")
