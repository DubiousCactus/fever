import os
import sys
import unittest

from fever import Fever


# INFO: Cases we want to handle:
# import foo
# from foo import bar where bar is a function
# from foo import bar where bar is a module
# from foo import bar where bar is a class
# from foo import * where we want to import the foo module basically
class TestImportHook(unittest.TestCase):
    def setUp(self):
        sys.path.append(os.path.join(os.getcwd(), "tests/test_imports"))
        self.fever = Fever()
        self.fever.setup()

    def tearDown(self):
        self.fever.cleanup()
        cleanup_modules = ["module_a", "module_b", "module_c", "module_d", "module_z"]
        for mod in list(sys.modules.keys()):
            if mod in cleanup_modules:
                del sys.modules[mod]

    def test_simple_wrong(self):
        self.assertRaises(ModuleNotFoundError, lambda: exec("import module_z"))
        self.assertFalse("module_z" in self.fever.dependency_tracker.all_imports)

    def test_simple(self):
        import module_d  # noqa: F401

        self.assertTrue("module_d" in self.fever.dependency_tracker.all_imports)

    def test_circular(self):
        import module_a  # noqa: F401

        self.assertTrue("module_a" in self.fever.dependency_tracker.all_imports)
        self.assertTrue("module_b" in self.fever.dependency_tracker.all_imports)
        self.assertTrue("module_c" in self.fever.dependency_tracker.all_imports)

    def test_from_import_function(self):
        from module_d import function_d  # noqa: F401

        print(self.fever.dependency_tracker.all_imports)
        self.assertTrue("module_d" in self.fever.dependency_tracker.all_imports)
        self.assertFalse(
            "module_d.function_d" in self.fever.dependency_tracker.all_imports
        )

    def test_from_import_function_with_circular(self):
        from module_a import second_function  # noqa: F401

        print(self.fever.dependency_tracker.all_imports)
        self.assertTrue("module_a" in self.fever.dependency_tracker.all_imports)

    def test_from_import_class(self):
        from module_b import TestCase  # noqa: F401

        self.assertTrue("module_b" in self.fever.dependency_tracker.all_imports)

    def test_from_import_module(self):
        from submodules import module_e  # noqa: F401

        self.assertTrue("module_e" in self.fever.dependency_tracker.all_imports)

    def test_from_import_class_nested(self):
        from module_b import NestedTestCase  # noqa: F401

        self.assertTrue("module_b" in self.fever.dependency_tracker.all_imports)
