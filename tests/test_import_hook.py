import os
import sys
import unittest

from fever import Fever


# Cases we want to handle:
# import foo
# from foo import bar where bar is a function
# from foo import bar where bar is a module
# from foo import bar where bar is a class
# from foo import * where we want to import the foo module basically
class TestImportHook(unittest.TestCase):
    def setUp(self):
        self.fever = Fever()
        self.fever.setup()

    def tearDown(self):
        self.fever.cleanup()

    def test_import_hook_simple(self):
        sys.path.append(os.path.join(os.getcwd(), "tests/test_imports"))
        import module_a  # noqa: F401

        self.assertTrue("module_a" in self.fever.dependency_tracker.all_imports)
