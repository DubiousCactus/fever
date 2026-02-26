import unittest
from unittest.mock import Mock
import warnings
from typing import Any, List, Optional

from fever.types import (
    FeverWarning,
    FeverClass,
    FeverFunction,
    FeverLambda,
    FeverImport,
    FeverGlobalVar,
    FeverModule,
    FeverParameters,
    FeverEntryPoint,
)


class TestFeverWarning(unittest.TestCase):
    def test_fever_warning_inheritance(self):
        """Test that FeverWarning inherits from Warning."""
        self.assertTrue(issubclass(FeverWarning, Warning))

    def test_fever_warning_creation(self):
        """Test FeverWarning can be created."""
        warning = FeverWarning("Test warning")
        self.assertEqual(str(warning), "Test warning")


class TestFeverClass(unittest.TestCase):
    def test_fever_class_creation(self):
        """Test FeverClass dataclass creation."""
        mock_obj = Mock()
        fever_class = FeverClass(
            name="TestClass", obj=mock_obj, hash=12345, code="class TestClass: pass"
        )

        self.assertEqual(fever_class.name, "TestClass")
        self.assertEqual(fever_class.obj, mock_obj)
        self.assertEqual(fever_class.hash, 12345)
        self.assertEqual(fever_class.code, "class TestClass: pass")

    def test_fever_class_hash(self):
        """Test FeverClass __hash__ method."""
        fever_class = FeverClass(
            name="TestClass", obj=Mock(), hash=12345, code="class TestClass: pass"
        )

        self.assertEqual(hash(fever_class), 12345)

    def test_fever_class_equality(self):
        """Test FeverClass equality based on hash."""
        class1 = FeverClass("Class1", Mock(), 12345, "code1")
        class2 = FeverClass("Class2", Mock(), 12345, "code2")
        class3 = FeverClass("Class3", Mock(), 67890, "code3")

        # Same hash should be equal
        self.assertEqual(class1, class2)

        # Different hash should not be equal
        self.assertNotEqual(class1, class3)


class TestFeverFunction(unittest.TestCase):
    def test_fever_function_creation(self):
        """Test FeverFunction dataclass creation."""
        mock_obj = Mock()
        args = ["arg1", "arg2"]
        fever_function = FeverFunction(
            name="test_function",
            args=args,
            obj=mock_obj,
            hash=54321,
            code="def test_function(): pass",
        )

        self.assertEqual(fever_function.name, "test_function")
        self.assertEqual(fever_function.args, args)
        self.assertEqual(fever_function.obj, mock_obj)
        self.assertEqual(fever_function.hash, 54321)
        self.assertEqual(fever_function.code, "def test_function(): pass")

    def test_fever_function_hash(self):
        """Test FeverFunction __hash__ method."""
        fever_function = FeverFunction(
            name="test_function",
            args=[],
            obj=Mock(),
            hash=54321,
            code="def test_function(): pass",
        )

        self.assertEqual(hash(fever_function), 54321)


class TestFeverLambda(unittest.TestCase):
    def test_fever_lambda_creation(self):
        """Test FeverLambda dataclass creation."""
        args = ["x", "y"]
        mock_obj = Mock()
        fever_lambda = FeverLambda(args=args, obj=mock_obj)

        self.assertEqual(fever_lambda.args, args)
        self.assertEqual(fever_lambda.obj, mock_obj)

    def test_fever_lambda_creation_without_obj(self):
        """Test FeverLambda creation without obj (default None)."""
        fever_lambda = FeverLambda(args=["x"])

        self.assertEqual(fever_lambda.args, ["x"])
        self.assertIsNone(fever_lambda.obj)


class TestFeverImport(unittest.TestCase):
    def test_fever_import_creation(self):
        """Test FeverImport dataclass creation."""
        fever_import = FeverImport(
            module="test_module",
            code="import test_module",
            alias="tm",
            sub_imports=["func1", "class1"],
        )

        self.assertEqual(fever_import.module, "test_module")
        self.assertEqual(fever_import.code, "import test_module")
        self.assertEqual(fever_import.alias, "tm")
        self.assertEqual(fever_import.sub_imports, ["func1", "class1"])

    def test_fever_import_creation_minimal(self):
        """Test FeverImport creation with minimal parameters."""
        fever_import = FeverImport(module="test_module", code="import test_module")

        self.assertEqual(fever_import.module, "test_module")
        self.assertEqual(fever_import.code, "import test_module")
        self.assertIsNone(fever_import.alias)
        self.assertIsNone(fever_import.sub_imports)


class TestFeverGlobalVar(unittest.TestCase):
    def test_fever_global_var_creation(self):
        """Test FeverGlobalVar dataclass creation."""
        fever_global = FeverGlobalVar(name="GLOBAL_VAR", value=42)

        self.assertEqual(fever_global.name, "GLOBAL_VAR")
        self.assertEqual(fever_global.value, 42)


class TestFeverModule(unittest.TestCase):
    def test_fever_module_creation(self):
        """Test FeverModule dataclass creation."""
        mock_obj = Mock()
        mock_class = Mock(spec=FeverClass)
        mock_function = Mock(spec=FeverFunction)
        mock_lambda = Mock(spec=FeverLambda)
        mock_import = Mock(spec=FeverImport)
        mock_global = Mock(spec=FeverGlobalVar)

        fever_module = FeverModule(
            name="test_module",
            obj=mock_obj,
            classes=[mock_class],
            functions=[mock_function],
            methods={mock_class: [mock_function]},
            lambdas=[mock_lambda],
            imports=[mock_import],
            globals=[mock_global],
        )

        self.assertEqual(fever_module.name, "test_module")
        self.assertEqual(fever_module.obj, mock_obj)
        self.assertEqual(fever_module.classes, [mock_class])
        self.assertEqual(fever_module.functions, [mock_function])
        self.assertEqual(fever_module.methods, {mock_class: [mock_function]})
        self.assertEqual(fever_module.lambdas, [mock_lambda])
        self.assertEqual(fever_module.imports, [mock_import])
        self.assertEqual(fever_module.globals, [mock_global])


class TestFeverParameters(unittest.TestCase):
    def test_fever_parameters_creation_simple(self):
        """Test FeverParameters creation with simple args."""
        params = FeverParameters(("arg1", "arg2"), {"kwarg1": "value1"})

        self.assertEqual(params.args, ("arg1", "arg2"))
        self.assertEqual(params.kwargs, {"kwarg1": "value1"})
        self.assertIsInstance(params.hash, int)

    def test_fever_parameters_make_immutable_dict(self):
        """Test that dictionaries are made immutable (frozenset)."""
        original_dict = {"key1": "value1", "key2": "value2"}
        params = FeverParameters((), original_dict)

        # kwargs should be a frozenset of key-value pairs
        self.assertIsInstance(params.kwargs, frozenset)

        # Check that the content is preserved
        kwargs_dict = dict(params.kwargs)
        self.assertEqual(kwargs_dict, original_dict)

    def test_fever_parameters_make_immutable_list(self):
        """Test that lists are made immutable (tuple)."""
        original_list = ["item1", "item2", "item3"]
        params = FeverParameters((original_list,), {})

        # args should contain a tuple
        self.assertIsInstance(params.args[0], tuple)
        self.assertEqual(params.args[0], ("item1", "item2", "item3"))

    def test_fever_parameters_make_immutable_set(self):
        """Test that sets are made immutable (frozenset)."""
        original_set = {"item1", "item2"}
        params = FeverParameters((), {"set_arg": original_set})

        # Extract the set from kwargs frozenset
        kwargs_dict = dict(params.kwargs)
        self.assertIsInstance(kwargs_dict["set_arg"], frozenset)
        self.assertEqual(set(kwargs_dict["set_arg"]), original_set)

    def test_fever_parameters_nested_structures(self):
        """Test FeverParameters with nested mutable structures."""
        nested_dict = {"nested": {"deep": "value"}}
        nested_list = [1, [2, 3], {"key": "val"}]

        params = FeverParameters((nested_list,), {"dict_arg": nested_dict})

        # Should not raise an error and should create a valid hash
        self.assertIsInstance(params.hash, int)

    def test_fever_parameters_hash_collision(self):
        """Test that different parameters can have the same hash (collision possible)."""
        params1 = FeverParameters(("arg1",), {"kwarg1": "value1"})
        params2 = FeverParameters(("arg2",), {"kwarg2": "value2"})

        # Hashes should be integers (they might be equal due to collision, but that's ok)
        self.assertIsInstance(params1.hash, int)
        self.assertIsInstance(params2.hash, int)

    def test_fever_parameters_unhashable_warning(self):
        """Test FeverParameters with unhashable arguments raises warning."""

        # Create a custom unhashable object
        class UnhashableObject:
            def __eq__(self, other):
                return True

        unhashable_obj = UnhashableObject()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            params = FeverParameters((unhashable_obj,), {})

            # Should have issued a warning
            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, FeverWarning))

            # Hash should be -1 when hashing fails
            self.assertEqual(params.hash, -1)

    def test_fever_parameters_hash_method(self):
        """Test FeverParameters __hash__ method."""
        params = FeverParameters(("arg1",), {"kwarg1": "value1"})

        # __hash__ should return the same as hash property
        self.assertEqual(hash(params), params.hash)

    def test_fever_parameters_str_short(self):
        """Test FeverParameters __str__ method with short content."""
        params = FeverParameters(("arg1",), {"kwarg1": "value1"})

        str_repr = str(params)
        self.assertIn("args=", str_repr)
        self.assertIn("kwargs=", str_repr)
        self.assertIn("arg1", str_repr)
        self.assertIn("value1", str_repr)

    def test_fever_parameters_str_long(self):
        """Test FeverParameters __str__ method with long content (truncated)."""
        long_args = tuple(f"arg{i}" for i in range(20))
        long_kwargs = {f"kwarg{i}": f"value{i}" for i in range(20)}

        params = FeverParameters(long_args, long_kwargs)

        str_repr = str(params)

        # Should be truncated
        self.assertTrue(len(str_repr) <= 30)
        self.assertTrue(str_repr.endswith("..."))

    def test_fever_parameters_empty(self):
        """Test FeverParameters with empty args and kwargs."""
        params = FeverParameters((), {})

        self.assertEqual(params.args, ())
        self.assertEqual(params.kwargs, frozenset())
        self.assertIsInstance(params.hash, int)


class TestFeverEntryPoint(unittest.TestCase):
    def test_fever_entry_point_creation(self):
        """Test FeverEntryPoint can be created (placeholder class)."""
        entry_point = FeverEntryPoint()
        self.assertIsNotNone(entry_point)


if __name__ == "__main__":
    unittest.main()
