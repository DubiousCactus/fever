import unittest


class TestImportHook(unittest.TestCase):
    def test_import_hook(self):
        # TODO: Make a little test suite :)
        # Cases we want to handle:
        # import foo
        # from foo import bar where bar is a function
        # from foo import bar where bar is a module
        # from foo import bar where bar is a class
        # from foo import * where we want to import the foo module basically
        self.assertTrue(False)
