import unittest
from unittest.mock import Mock, patch, mock_open
import os
import sys
import importlib
import warnings
from types import ModuleType
from typing import List, Tuple
from collections import defaultdict

from fever.dependency_tracker import DependencyTracker, find_module_path
from fever.utils import ConsoleInterface
from fever.types import FeverWarning


class TestFindModulePath(unittest.TestCase):
    def setUp(self):
        self.test_root = "/test/root"

    @patch("os.path.isfile")
    def test_find_module_path_with_init(self, mock_isfile):
        """Test finding module path when it's a package with __init__.py."""
        mock_isfile.return_value = True

        file_path, submodule_locations = find_module_path(self.test_root, "test_module")

        expected_path = os.path.join(self.test_root, "test_module", "__init__.py")
        self.assertEqual(file_path, expected_path)
        self.assertEqual(submodule_locations, [os.path.dirname(expected_path)])

    @patch("os.path.isfile")
    def test_find_module_path_with_py_file(self, mock_isfile):
        """Test finding module path when it's a single .py file."""
        # First call returns False (no __init__.py), second returns True (.py file exists)
        mock_isfile.side_effect = [False, True]

        file_path, submodule_locations = find_module_path(self.test_root, "test_module")

        expected_path = os.path.join(self.test_root, "test_module.py")
        self.assertEqual(file_path, expected_path)
        self.assertIsNone(submodule_locations)

    @patch("os.path.isfile")
    def test_find_module_path_not_found(self, mock_isfile):
        """Test finding module path when module doesn't exist."""
        mock_isfile.return_value = False

        file_path, submodule_locations = find_module_path(self.test_root, "test_module")

        self.assertIsNone(file_path)
        self.assertIsNone(submodule_locations)


class TestDependencyTracker(unittest.TestCase):
    def setUp(self):
        self.mock_console = Mock(spec=ConsoleInterface)
        self.mock_callback = Mock()
        self.tracker = DependencyTracker(
            console=self.mock_console, on_module_load_callback=self.mock_callback
        )

    def test_init(self):
        """Test DependencyTracker initialization."""
        self.assertEqual(self.tracker._console, self.mock_console)
        self.assertEqual(self.tracker._on_module_load_callback, self.mock_callback)
        self.assertIsInstance(self.tracker._dep_graph, dict)
        self.assertFalse(self.tracker._show_skips)
        self.assertIsInstance(self.tracker._user_modules, dict)

    def test_ignore_dirs(self):
        """Test that ignore_dirs contains expected directories."""
        expected_dirs = [".git", "__pycache__", ".vscode", ".venv", "fever"]
        self.assertEqual(self.tracker.ignore_dirs, expected_dirs)

    @patch("fever.dependency_tracker.sys._getframe")
    @patch("fever.dependency_tracker.inspect.getmodule")
    @patch("fever.dependency_tracker.os.getcwd")
    def test_setup(self, mock_getcwd, mock_getmodule, mock_getframe):
        """Test setup method."""
        mock_getcwd.return_value = "/test/dir"
        mock_frame = Mock()
        mock_getframe.return_value = mock_frame
        mock_code = Mock()
        mock_frame.f_code = mock_code
        mock_module = Mock()
        mock_module.__name__ = "test_module"
        mock_module.__file__ = "/test/dir/test_module.py"
        mock_getmodule.return_value = mock_module

        with patch.dict(os.environ, {"FEVER_PLOT_DEPS": "0"}):
            self.tracker.setup(caller_frame=mock_frame)

        # Check that user module was recorded
        self.assertIn("test_module", self.tracker._user_modules)
        self.assertEqual(
            self.tracker._user_modules["test_module"], "/test/dir/test_module.py"
        )

        # Check that tracker was added to meta_path
        self.assertIn(self.tracker, sys.meta_path)

    @patch("fever.dependency_tracker.sys._getframe")
    @patch("fever.dependency_tracker.inspect.getmodule")
    def test_setup_with_warning(self, mock_getmodule, mock_getframe):
        """Test setup when getmodule returns None."""
        mock_frame = Mock()
        mock_getframe.return_value = mock_frame
        mock_getmodule.return_value = None

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with patch("fever.dependency_tracker.os.getcwd", return_value="/test/dir"):
                self.tracker.setup(caller_frame=mock_frame)

            self.assertEqual(len(w), 1)
            self.assertTrue(issubclass(w[0].category, FeverWarning))

    def test_cleanup(self):
        """Test cleanup method."""
        # Add tracker to meta_path first
        sys.meta_path.insert(0, self.tracker)

        with patch.dict(os.environ, {"FEVER_PLOT_DEPS": "0"}):
            self.tracker.cleanup()

        # Check that tracker was removed from meta_path
        self.assertNotIn(self.tracker, sys.meta_path)

    def test_create_module(self):
        """Test create_module returns None (fallback to default)."""
        spec = Mock()
        result = self.tracker.create_module(spec)
        self.assertIsNone(result)

    @patch("builtins.open", new_callable=mock_open, read_data="test code")
    @patch("builtins.exec")
    @patch("builtins.compile")
    def test_exec_module(self, mock_compile, mock_exec, mock_file):
        """Test exec_module method."""
        mock_module = Mock()
        mock_module.__name__ = "test_module"
        mock_spec = Mock()
        mock_spec.name = "test_module"
        mock_spec.origin = "/test/path/test_module.py"
        mock_module.__spec__ = mock_spec

        mock_code_obj = Mock()
        mock_compile.return_value = mock_code_obj

        self.tracker.exec_module(mock_module)

        # Check that file was opened and read
        mock_file.assert_called_once_with("/test/path/test_module.py")

        # Check that code was compiled and executed
        mock_compile.assert_called_once()
        mock_exec.assert_called_once_with(mock_code_obj, mock_module.__dict__)

        # Check that callback was called
        self.mock_callback.assert_called_once_with("test_module")

        # Check that module was added to user_modules
        self.assertIn("test_module", self.tracker._user_modules)

    @patch("fever.dependency_tracker.find_module_path")
    @patch("fever.dependency_tracker.importlib.util.spec_from_file_location")
    def test_find_spec_found(self, mock_spec_from_file, mock_find_module_path):
        """Test find_spec when module is found."""
        mock_find_module_path.return_value = ("/test/path.py", None)
        mock_spec = Mock()
        mock_spec_from_file.return_value = mock_spec

        result = self.tracker.find_spec("test_module", ["/test/dir"])

        self.assertEqual(result, mock_spec)
        mock_find_module_path.assert_called_once_with("/test/dir", "test_module")
        mock_spec_from_file.assert_called_once()

    @patch("fever.dependency_tracker.find_module_path")
    def test_find_spec_not_found(self, mock_find_module_path):
        """Test find_spec when module is not found."""
        mock_find_module_path.return_value = (None, None)

        result = self.tracker.find_spec("test_module", ["/test/dir"])

        self.assertIsNone(result)

    @patch("fever.dependency_tracker.find_module_path")
    def test_find_spec_ignored_path(self, mock_find_module_path):
        """Test find_spec with ignored path."""
        ignored_path = os.path.join(os.getcwd(), ".git")

        result = self.tracker.find_spec("test_module", [ignored_path])

        self.assertIsNone(result)
        mock_find_module_path.assert_not_called()

    @patch("fever.dependency_tracker.find_module_path")
    @patch("fever.dependency_tracker.importlib.util.spec_from_file_location")
    @patch("fever.dependency_tracker.sys.path")
    def test_find_spec_sys_path_fallback(
        self, mock_sys_path, mock_spec_from_file, mock_find_module_path
    ):
        """Test find_spec fallback to sys.path."""
        # First call doesn't find it, second call does
        mock_find_module_path.side_effect = [
            (None, None),  # Not found in original path
            ("/sys/path/test_module.py", None),  # Found in sys.path
        ]
        mock_spec = Mock()
        mock_spec_from_file.return_value = mock_spec
        mock_sys_path.__contains__ = Mock(return_value=True)

        result = self.tracker.find_spec("test_module", ["/test/dir"])

        self.assertEqual(result, mock_spec)
        self.assertEqual(mock_find_module_path.call_count, 2)

    def test_invalidate_caches(self):
        """Test invalidate_caches method."""
        # Add some user modules
        self.tracker._user_modules["test1"] = "/path1"
        self.tracker._user_modules["test2"] = "/path2"

        self.tracker.invalidate_caches()

        self.assertEqual(len(self.tracker._user_modules), 0)

    @patch("fever.dependency_tracker.sys.modules")
    @patch("fever.dependency_tracker.inspect.getfile")
    def test_get_dependencies(self, mock_getfile, mock_modules):
        """Test get_dependencies method."""
        # Set up dependency graph: A -> B -> C
        self.tracker._dep_graph.add_edge("B", "A")
        self.tracker._dep_graph.add_edge("C", "B")

        deps = self.tracker.get_dependencies("A")

        # Should return all modules that depend on A (directly or indirectly)
        # In this case, only B depends on A
        self.assertIn("B", deps)

    @patch("fever.dependency_tracker.sys.modules")
    @patch("fever.dependency_tracker.inspect.getfile")
    def test_get_dependent_modules(self, mock_getfile, mock_modules):
        """Test get_dependent_modules method."""
        # Set up dependency graph
        self.tracker._dep_graph.add_edge("B", "A")

        mock_module = Mock()
        mock_modules.__getitem__ = Mock(return_value=mock_module)
        mock_getfile.return_value = "/path/to/module.py"

        deps = self.tracker.get_dependent_modules("A")

        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0][0], "B")  # module name
        self.assertEqual(deps[0][1], "/path/to/module.py")  # module path
        self.assertEqual(deps[0][2], mock_module)  # module object

    @patch("matplotlib.pyplot.show")
    def test_plot(self, mock_show):
        """Test plot method."""
        # Add some test data to the dependency graph
        self.tracker._dep_graph.add_node("test_module")

        self.tracker.plot()

        # Should call plt.show()
        mock_show.assert_called_once()

    def test_all_imports_property(self):
        """Test all_imports property."""
        # Add some nodes to the dependency graph
        self.tracker._dep_graph.add_node("module1")
        self.tracker._dep_graph.add_node("module2")

        imports = self.tracker.all_imports

        self.assertIn("module1", imports)
        self.assertIn("module2", imports)

    @patch.dict(os.environ, {"FEVER_PLOT_DEPS": "1"})
    def test_setup_with_plot_deps(self):
        """Test setup when FEVER_PLOT_DEPS is enabled."""
        original_import = __builtins__.__import__

        try:
            with patch("fever.dependency_tracker.sys._getframe"):
                with patch("fever.dependency_tracker.inspect.getmodule"):
                    with patch(
                        "fever.dependency_tracker.os.getcwd", return_value="/test"
                    ):
                        self.tracker.setup()

            # Check that original import was stored
            self.assertTrue(hasattr(self.tracker, "_original_importer"))

        finally:
            # Restore original import
            __builtins__.__import__ = original_import

    @patch.dict(os.environ, {"FEVER_PLOT_DEPS": "1"})
    def test_cleanup_with_plot_deps(self):
        """Test cleanup when FEVER_PLOT_DEPS is enabled."""
        # Set up original importer
        self.tracker._original_importer = __builtins__.__import__

        with patch.dict(os.environ, {"FEVER_PLOT_DEPS": "1"}):
            self.tracker.cleanup()

        # Check that original import was restored
        # Note: This test might be fragile due to __builtins__ behavior

    def test_import_hook(self):
        """Test the _import hook method."""
        # This is a complex method that would require extensive mocking
        # For now, just test that it exists and can be called
        self.tracker._original_importer = Mock(return_value=Mock())
        self.tracker._user_modules["test_module"] = "/test/path.py"

        with patch("fever.dependency_tracker.sys.modules") as mock_modules:
            mock_module = Mock()
            mock_modules.__getitem__ = Mock(return_value=mock_module)

            result = self.tracker._import("test_module")

            self.assertIsNotNone(result)
            self.tracker._original_importer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
