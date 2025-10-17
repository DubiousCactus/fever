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
        cleanup_modules = [
            "module_a",
            "module_b",
            "module_c",
            "module_d",
            "module_e",
            "module_z",
            "submodules",
            "submodules.module_e",
        ]
        for mod in list(sys.modules.keys()):
            if mod in cleanup_modules:
                del sys.modules[mod]
        for k in locals().keys():
            del locals()[k]

    def test_simple_wrong(self):
        self.assertRaises(ModuleNotFoundError, lambda: exec("import module_z"))
        self.assertFalse("module_z" in self.fever.dependency_tracker.all_imports)

    def test_simple(self):
        import module_d  # noqa: F401

        module_d.function_d("test")
        self.assertTrue("function_d" in dir(module_d))
        self.assertTrue("TestClass" in dir(module_d))
        self.assertTrue("NestedTestClass" in dir(getattr(module_d, "TestClass")))
        self.assertTrue("module_d" in self.fever.dependency_tracker.all_imports)

    def test_circular(self):
        import module_a  # noqa: F401

        module_a.function()
        self.assertTrue("function" in dir(module_a))
        self.assertTrue("second_function" in dir(module_a))
        self.assertTrue("module_a" in self.fever.dependency_tracker.all_imports)
        self.assertTrue("module_b" in self.fever.dependency_tracker.all_imports)
        self.assertTrue("module_c" in self.fever.dependency_tracker.all_imports)

    def test_from_import_function(self):
        from module_d import function_d  # noqa: F401

        function_d("test")
        self.assertTrue("function_d" in locals())
        self.assertTrue("module_d" in self.fever.dependency_tracker.all_imports)
        self.assertFalse(
            "module_d.function_d" in self.fever.dependency_tracker.all_imports
        )

    def test_from_import_function_with_circular(self):
        from module_a import second_function  # noqa: F401

        second_function()
        self.assertTrue("second_function" in locals())
        self.assertTrue("module_a" in self.fever.dependency_tracker.all_imports)
        self.assertFalse(
            "module_a.second_function" in self.fever.dependency_tracker.all_imports
        )

    def test_from_import_class(self):
        from module_d import TestClass  # noqa: F401

        t = TestClass()
        t()
        self.assertTrue("TestClass" in locals())
        self.assertTrue("module_d" in self.fever.dependency_tracker.all_imports)
        self.assertFalse(
            "module_d.TestClass" in self.fever.dependency_tracker.all_imports
        )

    def test_from_import_class_nested(self):
        from module_d import TestClass  # noqa: F401

        parent = TestClass()
        nt = TestClass.NestedTestClass(parent)  # noqa: F401
        nt.nested_test("nested")
        self.assertTrue("TestClass" in locals())
        self.assertTrue("module_d" in self.fever.dependency_tracker.all_imports)
        self.assertFalse(
            "module_d.TestClass" in self.fever.dependency_tracker.all_imports
        )
        self.assertFalse(
            "module_d.NestedTestClass" in self.fever.dependency_tracker.all_imports
        )

    def test_import_multiples(self):
        from module_d import TestClass, function_d  # noqa: F401

        t = TestClass()
        t.hello("tester")
        function_d("tester again")
        self.assertTrue("TestClass" in locals())
        self.assertTrue("function_d" in locals())
        self.assertTrue("module_d" in self.fever.dependency_tracker.all_imports)
        self.assertFalse(
            "module_d.function_d" in self.fever.dependency_tracker.all_imports
        )
        self.assertFalse(
            "module_d.TestClass" in self.fever.dependency_tracker.all_imports
        )

    def test_from_import_module(self):
        from submodules import module_e  # noqa: F401

        module_e.function_e()
        self.assertTrue("function_e" in dir(module_e))
        self.assertTrue("ClassE" in dir(module_e))
        self.assertTrue(
            "submodules.module_e" in self.fever.dependency_tracker.all_imports
        )

    def test_from_submodule_import_func(self):
        from submodules.module_e import function_e  # noqa: F401

        function_e()
        self.assertTrue("function_e" in locals())
        self.assertTrue(
            "submodules.module_e" in self.fever.dependency_tracker.all_imports
        )

    def test_from_submodule_import_class(self):
        from submodules.module_e import ClassE  # noqa: F401

        e = ClassE()
        e.method_e()
        self.assertTrue("ClassE" in locals())
        self.assertTrue(
            "submodules.module_e" in self.fever.dependency_tracker.all_imports
        )
