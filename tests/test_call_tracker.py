import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import timeit
import warnings
from types import FrameType
from typing import Optional

from fever.call_tracker import CallTracker, TrackingMode, get_caller_obj
from fever.ast_analysis import FeverFunction, FeverClass, FeverModule
from fever.types import FeverParameters, FeverWarning
from fever.registry import Registry
from fever.utils import ConsoleInterface


class TestTrackingMode(unittest.TestCase):
    def test_tracking_mode_values(self):
        """Test that TrackingMode enum has correct values."""
        self.assertTrue(hasattr(TrackingMode, "KV_POINTERS"))
        self.assertTrue(hasattr(TrackingMode, "KV_NAMES"))
        self.assertTrue(TrackingMode.KV_POINTERS != TrackingMode.KV_NAMES)


class TestGetCallerObj(unittest.TestCase):
    def test_get_caller_obj_with_self(self):
        """Test getting caller object when 'self' is in locals."""
        # Create a mock frame with 'self' in locals
        mock_frame = Mock(spec=FrameType)
        mock_self = Mock()
        mock_frame.f_locals = {"self": mock_self}
        mock_frame.f_code.co_name = "test_method"
        mock_frame.f_globals = {"__name__": "test_module"}

        # Mock the getattr chain
        mock_method = Mock()
        mock_self.__getattr__ = Mock(return_value=mock_method)

        with patch("fever.call_tracker.sys.modules") as mock_modules:
            mock_modules.__getitem__.return_value = mock_self

            result = get_caller_obj(mock_frame, "test_method")

            # Should return the method object
            self.assertIsNotNone(result)

    def test_get_caller_obj_main_module(self):
        """Test getting caller object from main module."""
        mock_frame = Mock(spec=FrameType)
        mock_frame.f_locals = {}
        mock_frame.f_globals = {"__name__": "__main__"}

        with patch("fever.call_tracker.sys.modules") as mock_modules:
            mock_main = Mock()
            mock_modules.__getitem__ = Mock(return_value=mock_main)

            result = get_caller_obj(mock_frame, "test_function")

            self.assertEqual(result, mock_main)

    def test_get_caller_obj_module_function(self):
        """Test getting caller object for module-level function."""
        mock_frame = Mock(spec=FrameType)
        mock_frame.f_locals = {}
        mock_frame.f_globals = {"__name__": "test_module"}

        mock_function = Mock()
        with patch("fever.call_tracker.sys.modules") as mock_modules:
            mock_module = Mock()
            mock_module.test_function = mock_function
            mock_modules.__getitem__ = Mock(return_value=mock_module)

            result = get_caller_obj(mock_frame, "test_function")

            self.assertEqual(result, mock_function)

    def test_get_caller_obj_exception(self):
        """Test get_caller_obj handles exceptions gracefully."""
        mock_frame = Mock(spec=FrameType)
        mock_frame.f_locals = {"self": Mock()}
        mock_frame.f_code.co_name = "test_method"
        mock_frame.f_globals = {"__name__": "test_module"}

        # Make getattr raise an exception
        with patch("fever.call_tracker.sys.modules") as mock_modules:
            mock_modules.__getitem__.side_effect = AttributeError("Test exception")

            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = get_caller_obj(mock_frame, "test_method")

                self.assertIsNone(result)
                self.assertEqual(len(w), 1)
                self.assertTrue(issubclass(w[0].category, FeverWarning))


class TestCallTracker(unittest.TestCase):
    def setUp(self):
        self.mock_registry = Mock(spec=Registry)
        self.mock_console = Mock(spec=ConsoleInterface)
        self.mock_on_new_call = Mock()

        self.call_tracker = CallTracker(
            registry=self.mock_registry,
            tracking_mode=TrackingMode.KV_NAMES,
            console=self.mock_console,
            with_cache=True,
            on_new_call=self.mock_on_new_call,
        )

    def test_init(self):
        """Test CallTracker initialization."""
        self.assertEqual(self.call_tracker._registry, self.mock_registry)
        self.assertEqual(self.call_tracker._tracking_mode, TrackingMode.KV_NAMES)
        self.assertEqual(self.call_tracker._console, self.mock_console)
        self.assertEqual(self.call_tracker._on_new_call, self.mock_on_new_call)
        self.assertIsNotNone(self.call_tracker._call_graph)
        self.assertIsNotNone(self.call_tracker._cache)

    def test_track_calls_wrapper(self):
        """Test that track_calls returns a wrapper function."""
        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_function"
        mock_func.obj = Mock(return_value="test_result")
        mock_module = Mock(spec=FeverModule)
        mock_module.name = "test_module"

        wrapper = self.call_tracker.track_calls(mock_func, mock_module)

        self.assertTrue(callable(wrapper))

    @patch("fever.call_tracker.sys._getframe")
    @patch("fever.call_tracker.timeit.default_timer")
    def test_track_calls_execution(self, mock_timer, mock_getframe):
        """Test the execution of tracked calls."""
        # Setup mocks
        mock_timer.side_effect = [0.0, 1.0]  # start and end times
        mock_frame = Mock(spec=FrameType)
        mock_frame.f_code.co_qualname = "caller_function"
        mock_frame.f_lineno = 42
        mock_getframe.return_value = mock_frame

        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_function"
        mock_func.obj = Mock(return_value="test_result")
        mock_module = Mock(spec=FeverModule)
        mock_module.name = "test_module"
        mock_module.obj = Mock()

        # Mock registry pointers
        self.mock_registry._FUNCTION_PTRS = {
            mock_module.name: {mock_func.name: mock_func.obj}
        }

        wrapper = self.call_tracker.track_calls(mock_func, mock_module)

        # Execute the wrapper
        result = wrapper("arg1", kwarg1="value1")

        # Verify result
        self.assertEqual(result, "test_result")

        # Verify console was called
        self.mock_console.print.assert_called()

        # Verify call graph was updated
        self.assertTrue(self.call_tracker._call_graph.has_node("caller_function"))
        self.assertTrue(self.call_tracker._call_graph.has_node("test_function"))
        self.assertTrue(
            self.call_tracker._call_graph.has_edge("caller_function", "test_function")
        )

    @patch("fever.call_tracker.sys._getframe")
    def test_track_calls_with_cache_hit(self, mock_getframe):
        """Test track_calls with cache hit."""
        mock_frame = Mock(spec=FrameType)
        mock_frame.f_code.co_qualname = "caller_function"
        mock_frame.f_lineno = 42
        mock_getframe.return_value = mock_frame

        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_function"
        mock_func.obj = Mock()
        mock_module = Mock(spec=FeverModule)
        mock_module.name = "test_module"

        mock_params = Mock(spec=FeverParameters)
        mock_params.hash = "test_hash"

        # Mock cache hit
        self.call_tracker._cache.get = Mock(return_value="cached_result")

        wrapper = self.call_tracker.track_calls(mock_func, mock_module)

        with patch("fever.call_tracker.FeverParameters") as mock_params_class:
            mock_params_class.return_value = mock_params

            result = wrapper("arg1")

            self.assertEqual(result, "cached_result")
            self.call_tracker._cache.get.assert_called_once()
            # Original function should not be called
            mock_func.obj.assert_not_called()

    @patch("fever.call_tracker.sys._getframe")
    @patch("fever.call_tracker.timeit.default_timer")
    def test_track_calls_edge_statistics(self, mock_timer, mock_getframe):
        """Test that edge statistics are properly recorded."""
        mock_timer.side_effect = [0.0, 2.0]  # 2 second execution time
        mock_frame = Mock(spec=FrameType)
        mock_frame.f_code.co_qualname = "caller_function"
        mock_frame.f_lineno = 42
        mock_getframe.return_value = mock_frame

        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_function"
        mock_func.obj = Mock(return_value="test_result")
        mock_module = Mock(spec=FeverModule)
        mock_module.name = "test_module"

        # Mock registry pointers
        self.mock_registry._FUNCTION_PTRS = {
            mock_module.name: {mock_func.name: mock_func.obj}
        }

        wrapper = self.call_tracker.track_calls(mock_func, mock_module)

        with patch("fever.call_tracker.FeverParameters") as mock_params_class:
            mock_params = Mock()
            mock_params.hash = "test_hash"
            mock_params_class.return_value = mock_params

            # Call twice to test cumulative statistics
            wrapper("arg1")
            wrapper("arg1")

            # Check edge data
            edge_data = self.call_tracker._call_graph.edges[
                "caller_function", "test_function", "test_hash"
            ]
            self.assertEqual(edge_data["calls"], 2)
            self.assertEqual(edge_data["cum_time"], 4.0)  # 2 + 2 seconds
            self.assertEqual(edge_data["weight"], 2.0)  # 4.0 / 2

    def test_track_calls_with_class(self):
        """Test track_calls with a class method."""
        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_method"
        mock_func.obj = Mock(return_value="method_result")
        mock_class = Mock(spec=FeverClass)
        mock_class.name = "TestClass"
        mock_module = Mock(spec=FeverModule)
        mock_module.name = "test_module"

        # Mock registry pointers for class method
        self.mock_registry._CLASS_METHOD_PTRS = {
            mock_module.name: {mock_class.name: {mock_func.name: mock_func.obj}}
        }

        wrapper = self.call_tracker.track_calls(mock_func, mock_module, mock_class)

        self.assertTrue(callable(wrapper))

    @patch("fever.call_tracker.sys._getframe")
    def test_track_calls_kv_pointers_mode(self, mock_getframe):
        """Test track_calls in KV_POINTERS mode."""
        mock_frame = Mock(spec=FrameType)
        mock_frame.f_code.co_qualname = "caller_function"
        mock_frame.f_lineno = 42
        mock_getframe.return_value = mock_frame

        # Create tracker with KV_POINTERS mode
        tracker = CallTracker(
            registry=self.mock_registry,
            tracking_mode=TrackingMode.KV_POINTERS,
            console=self.mock_console,
            with_cache=False,
            on_new_call=self.mock_on_new_call,
        )

        mock_func = Mock(spec=FeverFunction)
        mock_func.name = "test_function"
        mock_func.obj = Mock(return_value="test_result")
        mock_module = Mock(spec=FeverModule)
        mock_module.name = "test_module"

        # Mock registry pointers
        self.mock_registry._FUNCTION_PTRS = {
            mock_module.name: {mock_func.name: mock_func.obj}
        }

        wrapper = tracker.track_calls(mock_func, mock_module)

        with patch("fever.call_tracker.get_caller_obj") as mock_get_caller_obj:
            mock_caller_obj = Mock()
            mock_get_caller_obj.return_value = mock_caller_obj

            with patch("fever.call_tracker.FeverParameters") as mock_params_class:
                mock_params = Mock()
                mock_params.hash = "test_hash"
                mock_params_class.return_value = mock_params

                result = wrapper("arg1")

                # Should use object pointers as nodes
                self.assertTrue(tracker._call_graph.has_node(mock_caller_obj))
                self.assertTrue(tracker._call_graph.has_node(mock_func.obj))

    def test_single_edge_call_graph(self):
        """Test single_edge_call_graph property."""
        # Add some edges to the call graph
        self.call_tracker._call_graph.add_edge(
            "A", "B", key="params1", cum_time=1.0, calls=1, weight=1.0
        )
        self.call_tracker._call_graph.add_edge(
            "A", "B", key="params2", cum_time=2.0, calls=1, weight=2.0
        )
        self.call_tracker._call_graph.add_edge(
            "B", "C", key="params3", cum_time=0.5, calls=1, weight=0.5
        )

        single_graph = self.call_tracker.single_edge_call_graph

        # Should merge multiple edges between same nodes
        self.assertTrue(single_graph.has_edge("A", "B"))
        self.assertTrue(single_graph.has_edge("B", "C"))

        # Check aggregated statistics for A->B
        edge_data = single_graph.edges["A", "B"]
        self.assertEqual(edge_data["cum_time"], 3.0)  # 1.0 + 2.0
        self.assertEqual(edge_data["calls"], 2)  # 1 + 1
        self.assertEqual(edge_data["weight"], 1.5)  # 3.0 / 2

    @patch("matplotlib.pyplot.show")
    def test_plot(self, mock_show):
        """Test plot method."""
        # Add some test data to the call graph
        self.call_tracker._call_graph.add_edge("A", "B", key="params1")

        self.call_tracker.plot()

        # Should call plt.show()
        mock_show.assert_called_once()

    def test_track_calls_generic_function_error(self):
        """Test that generic_function raises an error."""
        from fever.ast_analysis import generic_function

        mock_func = Mock()
        mock_func.obj = generic_function
        mock_module = Mock(spec=FeverModule)

        wrapper = self.call_tracker.track_calls(mock_func, mock_module)

        with self.assertRaises(RuntimeError):
            wrapper()


if __name__ == "__main__":
    unittest.main()
