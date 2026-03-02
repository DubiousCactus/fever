import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import warnings
from types import FrameType, ModuleType
from typing import Callable, Dict, Optional
from uuid import UUID

from fever.core import FeverCore, compile_code_in_namespace
from fever.ast_analysis import FeverFunction, FeverClass, FeverModule, generic_function
from fever.registry import Registry
from fever.dependency_tracker import DependencyTracker
from fever.call_tracker import CallTracker, TrackingMode
from fever.types import FeverWarning


class TestCompileCodeInNamespace(unittest.TestCase):
    def test_compile_code_in_namespace(self):
        """Test compile_code_in_namespace function."""
        code = "def test_func():\n    return 'test_result'"
        callable_name = "test_func"
        module_namespace = {}
        registry_namespace = {}

        compile_code_in_namespace(
            code, callable_name, module_namespace, registry_namespace
        )

        # Check that function was compiled into registry namespace
        self.assertIn(callable_name, registry_namespace)
        self.assertTrue(callable(registry_namespace[callable_name]))
        self.assertEqual(registry_namespace[callable_name](), "test_result")

    def test_compile_code_in_namespace_with_globals(self):
        """Test compile_code_in_namespace with global variables."""
        code = "GLOBAL_VAR = 42\ndef test_func():\n    return GLOBAL_VAR"
        callable_name = "test_func"
        module_namespace = {}
        registry_namespace = {}

        compile_code_in_namespace(
            code, callable_name, module_namespace, registry_namespace
        )

        # Check that function can access global variables
        self.assertEqual(registry_namespace["test_func"](), 42)


class TestFeverCore(unittest.TestCase):
    def setUp(self):
        with patch("fever.core.parse_verbosity", return_value=1):
            with patch("fever.core.ConsoleInterface"):
                with patch("fever.core.ASTAnalyzer"):
                    with patch("fever.core.Registry"):
                        with patch("fever.core.DependencyTracker"):
                            with patch("fever.core.CallTracker"):
                                self.core = FeverCore()

    def test_init(self):
        """Test FeverCore initialization."""
        self.assertIsNotNone(self.core._console_if)
        self.assertIsNotNone(self.core._ast_analyzer)
        self.assertIsNotNone(self.core.registry)
        self.assertIsNotNone(self.core.dependency_tracker)
        self.assertIsNotNone(self.core._call_tracker)

    def test_init_with_custom_console(self):
        """Test FeverCore initialization with custom console."""
        from rich.console import Console

        with patch("fever.core.parse_verbosity", return_value=1):
            with patch("fever.core.ConsoleInterface"):
                with patch("fever.core.ASTAnalyzer"):
                    with patch("fever.core.Registry"):
                        with patch("fever.core.DependencyTracker"):
                            with patch("fever.core.CallTracker"):
                                custom_console = Console()
                                core = FeverCore(rich_console=custom_console)
                                self.assertIsNotNone(core)

    def test_setup(self):
        """Test setup method."""
        with patch.object(self.core.dependency_tracker, "setup") as mock_setup:
            self.core.setup()
            mock_setup.assert_called_once()

    def test_cleanup(self):
        """Test cleanup method."""
        with patch.object(self.core.dependency_tracker, "cleanup") as mock_cleanup:
            with patch.object(self.core.registry, "cleanup") as mock_registry_cleanup:
                self.core.cleanup()
                mock_cleanup.assert_called_once()
                mock_registry_cleanup.assert_called_once()

    @patch("fever.core.sys.modules")
    def test_on_module_load_success(self, mock_modules):
        """Test on_module_load when module is found."""
        mock_module = Mock()
        mock_module.__name__ = "test_module"
        mock_modules.__getitem__ = Mock(return_value=mock_module)

        mock_fever_module = Mock(spec=FeverModule)
        mock_fever_module.obj = mock_module
        self.core._ast_analyzer.make_module_inventory = Mock(
            return_value=mock_fever_module
        )

        with patch.object(self.core.registry, "add_module") as mock_add:
            with patch.object(self.core, "_track_module") as mock_track:
                self.core.on_module_load("test_module")

                mock_add.assert_called_once_with("test_module", mock_fever_module)
                mock_track.assert_called_once_with(mock_fever_module)

    @patch("fever.core.sys.modules")
    def test_on_module_load_not_found(self, mock_modules):
        """Test on_module_load when module is not found."""
        mock_modules.__getitem__ = Mock(side_effect=KeyError("Module not found"))

        with self.assertRaises(RuntimeError):
            self.core.on_module_load("nonexistent_module")

    def test_on_new_import(self):
        """Test on_new_import method (placeholder)."""
        # This method is currently a placeholder
        self.core.on_new_import("test_module", Mock())
        # Should not raise any errors

    def test_plot_dependency_graph(self):
        """Test plot_dependency_graph method."""
        with patch.object(self.core.dependency_tracker, "plot") as mock_plot:
            self.core.plot_dependency_graph()
            mock_plot.assert_called_once()

    def test_plot_call_graph(self):
        """Test plot_call_graph method."""
        with patch.object(self.core._call_tracker, "plot") as mock_plot:
            self.core.plot_call_graph()
            mock_plot.assert_called_once()

    def test_track_module(self):
        """Test _track_module method."""
        mock_module = Mock(spec=FeverModule)
        mock_func = Mock(spec=FeverFunction)
        mock_class = Mock(spec=FeverClass)
        mock_method = Mock(spec=FeverFunction)

        mock_module.functions = [mock_func]
        mock_module.classes = [mock_class]
        mock_module.methods = {mock_class: [mock_method]}

        with patch.object(self.core, "_track_function") as mock_track_func:
            with patch.object(self.core, "_track_class") as mock_track_class:
                with patch.object(self.core, "_track_method") as mock_track_method:
                    self.core._track_module(mock_module)

                    mock_track_func.assert_called_once_with(mock_func, mock_module)
                    mock_track_class.assert_called_once_with(mock_class, mock_module)
                    mock_track_method.assert_called_once_with(
                        mock_method, mock_class, mock_module
                    )

    def test_track_function_success(self):
        """Test _track_function when tracking succeeds."""
        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_function"
        mock_func.obj = Mock(return_value="test")
        mock_func.hash = "abc123"

        mock_module = Mock(spec=FeverModule)
        mock_module.obj = Mock()
        mock_module.obj.test_function = mock_func.obj

        with patch.object(self.core._call_tracker, "track_calls") as mock_track:
            mock_track.return_value = Mock()

            self.core._track_function(mock_func, mock_module)

            mock_track.assert_called_once_with(mock_func, mock_module)

    def test_track_function_already_wrapped(self):
        """Test _track_function when function is already wrapped."""
        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_function"
        mock_func.obj = Mock()

        mock_module = Mock(spec=FeverModule)
        mock_module.obj = Mock()
        mock_wrapper = Mock()
        mock_wrapper.__wrapped__ = Mock()
        mock_module.obj.test_function = mock_wrapper

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.core._track_function(mock_func, mock_module)

            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, FeverWarning))

    def test_track_function_generic_function(self):
        """Test _track_function with generic_function."""
        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_function"
        mock_func.obj = generic_function

        mock_module = Mock(spec=FeverModule)
        mock_module.obj = Mock()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.core._track_function(mock_func, mock_module)

            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, FeverWarning))

    def test_track_function_not_callable(self):
        """Test _track_function when function is not callable."""
        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_function"
        mock_func.obj = "not_callable"  # String instead of callable

        mock_module = Mock(spec=FeverModule)
        mock_module.obj = Mock()
        mock_module.obj.test_function = mock_func.obj

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.core._track_function(mock_func, mock_module)

            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, FeverWarning))

    def test_track_method_success(self):
        """Test _track_method when tracking succeeds."""
        mock_method = Mock(spec=FeverFunction)
        mock_method.name = "test_method"
        mock_method.obj = Mock(return_value="method_result")

        mock_class = Mock(spec=FeverClass)
        mock_class.name = "TestClass"

        mock_module = Mock(spec=FeverModule)
        mock_module.obj = Mock()
        mock_class_obj = Mock()
        mock_class_obj.test_method = mock_method.obj
        mock_module.obj.TestClass = mock_class_obj

        with patch.object(self.core._call_tracker, "track_calls") as mock_track:
            mock_track.return_value = Mock()

            self.core._track_method(mock_method, mock_class, mock_module)

            mock_track.assert_called_once_with(mock_method, mock_module, mock_class)

    def test_track_class(self):
        """Test _track_class method."""
        mock_class = Mock(spec=FeverClass)
        mock_class.name = "TestClass"
        mock_class.obj = Mock()

        mock_module = Mock(spec=FeverModule)
        mock_module.obj = Mock()

        self.core._track_class(mock_class, mock_module)

        # Check that class was added to module
        self.assertEqual(mock_module.obj.TestClass, mock_class.obj)

    @patch.object(FeverCore, "_handle_new_imports")
    @patch.object(FeverCore, "_add_new_globals")
    @patch.object(FeverCore, "_reload_functions")
    @patch.object(FeverCore, "_reload_classes_and_methods")
    def test_reload(
        self,
        mock_reload_classes,
        mock_reload_funcs,
        mock_add_globals,
        mock_handle_imports,
    ):
        """Test reload method."""
        # Mock dependency tracker
        self.core.dependency_tracker.all_imports = ["module1", "module2"]

        with patch("fever.core.sys.modules") as mock_modules:
            mock_module = Mock()
            mock_module.__file__ = "/test/path.py"
            mock_modules.__getitem__ = Mock(return_value=mock_module)

            mock_fever_module = Mock(spec=FeverModule)
            self.core._ast_analyzer.make_module_inventory = Mock(
                return_value=mock_fever_module
            )

            self.core.reload()

            # Should process all modules
            self.assertEqual(mock_reload_funcs.call_count, 2)
            self.assertEqual(mock_reload_classes.call_count, 2)
            self.assertEqual(mock_handle_imports.call_count, 2)
            self.assertEqual(mock_add_globals.call_count, 2)

    def test_reload_with_module_list(self):
        """Test reload with specific module list."""
        module_list = ["module1"]
        self.core.dependency_tracker.all_imports = ["module1", "module2"]

        with patch("fever.core.sys.modules") as mock_modules:
            mock_module = Mock()
            mock_module.__file__ = "/test/path.py"
            mock_modules.__getitem__ = Mock(return_value=mock_module)

            mock_fever_module = Mock(spec=FeverModule)
            self.core._ast_analyzer.make_module_inventory = Mock(
                return_value=mock_fever_module
            )

            with patch.object(self.core, "_reload_functions") as mock_reload:
                self.core.reload(module_list)

                # Should only process specified module
                mock_reload.assert_called_once()

    def test_reload_functions(self):
        """Test _reload_functions method."""
        mock_module = Mock()
        module_name = "test_module"

        mock_fever_module = Mock(spec=FeverModule)
        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_function"
        mock_func.code = "def test_func(): return 'new'"
        mock_func.hash = "new_hash"
        mock_fever_module.functions = [mock_func]

        # Mock existing function in registry
        existing_func = Mock(spec=FeverFunction)
        existing_func.name = "test_function"
        existing_func.hash = "old_hash"
        self.core.registry.find_function_by_name = Mock(return_value=existing_func)
        self.core.registry._FUNCTION_PTRS = {module_name: {"test_function": Mock()}}

        with patch("fever.core.compile_code_in_namespace") as mock_compile:
            self.core._reload_functions(module_name, mock_module, mock_fever_module)

            mock_compile.assert_called_once()

    def test_reload_classes_and_methods(self):
        """Test _reload_classes_and_methods method."""
        mock_module = Mock()
        module_name = "test_module"

        mock_class = Mock(spec=FeverClass)
        mock_class.name = "TestClass"
        mock_class.code = "class TestClass: pass"
        mock_method = Mock(spec=FeverFunction)
        mock_method.name = "test_method"
        mock_method.code = "def test_method(self): pass"
        mock_method.hash = "new_hash"

        mock_fever_module = Mock(spec=FeverModule)
        mock_fever_module.methods = {mock_class: [mock_method]}

        # Mock existing class and method in registry
        self.core.registry._CLASS_PTRS = {module_name: {"TestClass": Mock()}}
        self.core.registry._CLASS_METHOD_PTRS = {
            module_name: {"TestClass": {"test_method": Mock()}}
        }

        existing_method = Mock(spec=FeverFunction)
        existing_method.name = "test_method"
        existing_method.hash = "old_hash"
        self.core.registry.find_method_by_name = Mock(return_value=existing_method)
        self.core.registry.find_class_by_name = Mock(return_value=mock_class)

        with patch("fever.core.compile_code_in_namespace") as mock_compile:
            self.core._reload_classes_and_methods(
                module_name, mock_module, mock_fever_module
            )

            mock_compile.assert_called()

    def test_handle_new_imports(self):
        """Test _handle_new_imports method."""
        mock_module = {}
        module_name = "test_module"

        mock_import = Mock()
        mock_import.module = "new_module"
        mock_import.code = "import new_module"
        mock_fever_module = Mock(spec=FeverModule)
        mock_fever_module.imports = [mock_import]

        # Mock that import is not found in registry
        self.core.registry.find_import_by_name_or_alias = Mock(return_value=None)

        with patch("builtins.exec") as mock_exec:
            self.core._handle_new_imports(module_name, mock_module, mock_fever_module)

            mock_exec.assert_called_once_with(mock_import.code, mock_module)

    def test_add_new_globals(self):
        """Test _add_new_globals method."""
        mock_module = {}

        mock_global = Mock()
        mock_global.name = "new_global"
        mock_global.value = 42
        mock_fever_module = Mock(spec=FeverModule)
        mock_fever_module.globals = [mock_global]

        self.core._add_new_globals(mock_module, mock_fever_module)

        self.assertEqual(mock_module["new_global"], 42)

    def test_set_on_new_call_callback(self):
        """Test set_on_new_call_callback method."""
        mock_callback = Mock()

        self.core.set_on_new_call_callback(mock_callback)

        self.assertEqual(self.core._call_tracker._on_new_call, mock_callback)

    def test_export_trace(self):
        """Test export_trace method."""
        mock_graph = Mock()
        self.core._call_tracker.single_edge_call_graph = mock_graph

        with patch("builtins.open", mock_open()) as mock_file:
            with patch("pickle.dump") as mock_dump:
                self.core.export_trace("test_trace.pkl")

                mock_file.assert_called_once_with("test_trace.pkl", "wb")
                mock_dump.assert_called_once_with(
                    mock_graph, mock_file.return_value.__enter__.return_value
                )

    def test_rerun_not_implemented(self):
        """Test rerun method raises NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.core.rerun(UUID("12345678-1234-5678-1234-567812345678"))


if __name__ == "__main__":
    unittest.main()
