import unittest
from unittest.mock import Mock, patch
from collections import defaultdict

from fever.registry import Registry
from fever.ast_analysis import FeverFunction, FeverClass, FeverImport, FeverModule


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = Registry()

        # Create mock objects for testing
        self.mock_function = Mock(spec=FeverFunction)
        self.mock_function.name = "test_function"
        self.mock_function.obj = lambda: "test"
        self.mock_function.hash = "abc123"

        self.mock_class = Mock(spec=FeverClass)
        self.mock_class.name = "TestClass"
        self.mock_class.obj = Mock()
        self.mock_class.hash = "def456"

        self.mock_method = Mock(spec=FeverFunction)
        self.mock_method.name = "test_method"
        self.mock_method.obj = lambda self: "method_test"
        self.mock_method.hash = "ghi789"

        self.mock_import = Mock(spec=FeverImport)
        self.mock_import.module = "test_module"
        self.mock_import.alias = "tm"

        self.mock_module = Mock(spec=FeverModule)
        self.mock_module.name = "test_module"
        self.mock_module.functions = [self.mock_function]
        self.mock_module.classes = [self.mock_class]
        self.mock_module.methods = {self.mock_class: [self.mock_method]}
        self.mock_module.imports = [self.mock_import]

    def test_init(self):
        """Test Registry initialization."""
        self.assertEqual(len(self.registry._inventory), 0)
        self.assertIsInstance(self.registry._FUNCTION_PTRS, defaultdict)
        self.assertIsInstance(self.registry._CLASS_METHOD_PTRS, defaultdict)
        self.assertIsInstance(self.registry._CLASS_PTRS, defaultdict)

    def test_cleanup(self):
        """Test Registry cleanup."""
        # Add some data first
        self.registry._FUNCTION_PTRS["test"]["func"] = Mock()
        self.registry._CLASS_METHOD_PTRS["test"]["cls"] = {"method": Mock()}
        self.registry._CLASS_PTRS["test"]["cls"] = Mock()

        self.registry.cleanup()

        self.assertEqual(len(self.registry._FUNCTION_PTRS), 0)
        self.assertEqual(len(self.registry._CLASS_METHOD_PTRS), 0)
        self.assertEqual(len(self.registry._CLASS_PTRS), 0)

    def test_add_module(self):
        """Test adding a module to the registry."""
        self.registry.add_module("test_module", self.mock_module)

        self.assertIn("test_module", self.registry._inventory)
        self.assertEqual(self.registry._inventory["test_module"], self.mock_module)

        # Check that pointers were added
        self.assertIn("test_function", self.registry._FUNCTION_PTRS["test_module"])
        self.assertIn("TestClass", self.registry._CLASS_PTRS["test_module"])
        self.assertIn(
            "test_method", self.registry._CLASS_METHOD_PTRS["test_module"]["TestClass"]
        )

    def test_add_function(self):
        """Test adding a function to the registry."""
        # Add module first
        self.registry._inventory["test_module"] = self.mock_module

        self.registry.add_function("test_module", self.mock_function)

        self.assertIn(
            self.mock_function, self.registry._inventory["test_module"].functions
        )
        self.assertIn("test_function", self.registry._FUNCTION_PTRS["test_module"])

    def test_add_function_with_generic_function(self):
        """Test that adding generic_function raises an error."""
        from fever.ast_analysis import generic_function

        with self.assertRaises(AssertionError):
            self.registry.add_function("test_module", generic_function)

    def test_add_class(self):
        """Test adding a class to the registry."""
        # Add module first
        self.registry._inventory["test_module"] = self.mock_module

        self.registry.add_class("test_module", self.mock_class)

        self.assertIn(self.mock_class, self.registry._inventory["test_module"].classes)
        self.assertIn("TestClass", self.registry._CLASS_PTRS["test_module"])

    def test_add_method(self):
        """Test adding a method to the registry."""
        # Add module first
        self.registry._inventory["test_module"] = self.mock_module

        self.registry.add_method("test_module", self.mock_class, self.mock_method)

        self.assertIn(
            self.mock_method,
            self.registry._inventory["test_module"].methods[self.mock_class],
        )
        self.assertIn(
            "test_method", self.registry._CLASS_METHOD_PTRS["test_module"]["TestClass"]
        )

    def test_add_import(self):
        """Test adding an import to the registry."""
        # Add module first
        self.registry._inventory["test_module"] = self.mock_module

        self.registry.add_import("test_module", self.mock_import)

        self.assertIn(self.mock_import, self.registry._inventory["test_module"].imports)

    def test_find_function_by_name(self):
        """Test finding a function by name."""
        # Add module and function
        self.registry._inventory["test_module"] = self.mock_module
        self.registry._inventory["test_module"].functions = [self.mock_function]

        found = self.registry.find_function_by_name("test_function", "test_module")
        self.assertEqual(found, self.mock_function)

        # Test not found
        not_found = self.registry.find_function_by_name("nonexistent", "test_module")
        self.assertIsNone(not_found)

    def test_find_class_by_name(self):
        """Test finding a class by name."""
        # Add module and class
        self.registry._inventory["test_module"] = self.mock_module
        self.registry._inventory["test_module"].classes = [self.mock_class]

        found = self.registry.find_class_by_name("TestClass", "test_module")
        self.assertEqual(found, self.mock_class)

        # Test not found
        not_found = self.registry.find_class_by_name("Nonexistent", "test_module")
        self.assertIsNone(not_found)

    def test_find_method_by_name(self):
        """Test finding a method by name."""
        # Add module, class, and method
        self.registry._inventory["test_module"] = self.mock_module
        self.registry._inventory["test_module"].methods = {
            self.mock_class: [self.mock_method]
        }

        found = self.registry.find_method_by_name(
            "test_method", "TestClass", "test_module"
        )
        self.assertEqual(found, self.mock_method)

        # Test not found
        not_found = self.registry.find_method_by_name(
            "nonexistent", "TestClass", "test_module"
        )
        self.assertIsNone(not_found)

    def test_find_import_by_name_or_alias(self):
        """Test finding an import by name or alias."""
        # Add module and import
        self.registry._inventory["test_module"] = self.mock_module
        self.registry._inventory["test_module"].imports = [self.mock_import]

        # Test by name
        found_by_name = self.registry.find_import_by_name_or_alias(
            "test_module", "test_module"
        )
        self.assertEqual(found_by_name, self.mock_import)

        # Test by alias
        found_by_alias = self.registry.find_import_by_name_or_alias(
            "test_module", "test_module", "tm"
        )
        self.assertEqual(found_by_alias, self.mock_import)

        # Test not found
        not_found = self.registry.find_import_by_name_or_alias(
            "nonexistent", "test_module"
        )
        self.assertIsNone(not_found)

    def test_add_function_code_pointer(self):
        """Test adding function code pointers."""
        self.registry._add_function_code_pointer("test_module", self.mock_function)

        self.assertIn("test_function", self.registry._FUNCTION_PTRS["test_module"])
        self.assertEqual(
            self.registry._FUNCTION_PTRS["test_module"]["test_function"],
            self.mock_function.obj,
        )

    def test_add_class_code_pointer(self):
        """Test adding class code pointers."""
        self.registry._add_class_code_pointer("test_module", self.mock_class)

        self.assertIn("TestClass", self.registry._CLASS_PTRS["test_module"])
        self.assertEqual(
            self.registry._CLASS_PTRS["test_module"]["TestClass"], self.mock_class.obj
        )

    def test_add_method_code_pointer(self):
        """Test adding method code pointers."""
        self.registry._add_method_code_pointer(
            "test_module", self.mock_class, self.mock_method
        )

        self.assertIn("TestClass", self.registry._CLASS_METHOD_PTRS["test_module"])
        self.assertIn(
            "test_method", self.registry._CLASS_METHOD_PTRS["test_module"]["TestClass"]
        )
        self.assertEqual(
            self.registry._CLASS_METHOD_PTRS["test_module"]["TestClass"]["test_method"],
            self.mock_method.obj,
        )


if __name__ == "__main__":
    unittest.main()
