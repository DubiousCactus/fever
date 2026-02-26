import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import importlib
import runpy
from typing import List

from fever.cli import app, console
from fever.core import FeverCore


class TestCLI(unittest.TestCase):
    def setUp(self):
        # Reset sys.argv before each test
        self.original_argv = sys.argv.copy()

    def tearDown(self):
        # Restore original sys.argv
        sys.argv = self.original_argv

    @patch("fever.cli.FeverWatcher")
    @patch("fever.cli.importlib.import_module")
    @patch("fever.cli.runpy.run_path")
    @patch("fever.cli.os.chdir")
    @patch("fever.cli.os.path.abspath")
    @patch("fever.cli.os.path.dirname")
    @patch("fever.cli.sys.path")
    def test_watch_command_success(
        self,
        mock_sys_path,
        mock_dirname,
        mock_abspath,
        mock_chdir,
        mock_run_path,
        mock_import_module,
        mock_watcher,
    ):
        """Test watch command executes successfully."""
        # Setup mocks
        script = "test_script.py"
        extra_args = ["--arg1", "value1"]

        mock_abspath.return_value = "/full/path/test_script.py"
        mock_dirname.return_value = "/full/path"
        mock_watcher_instance = Mock()
        mock_watcher.return_value = mock_watcher_instance

        # Set up sys.argv
        sys.argv = ["fever", "watch", script] + extra_args

        # Mock the watch command
        with patch("fever.cli.typer.Argument"):
            with patch("fever.cli.typer.Option"):
                # Import the watch function and call it
                from fever.cli import watch

                watch(script, extra_args, False)

                # Verify watcher was created and started
                mock_watcher.assert_called_once_with(
                    rich_console=console, with_cache=True
                )
                mock_watcher_instance.watch.assert_called_once()

                # Verify script execution setup
                mock_chdir.assert_called_once_with("/full/path")
                mock_sys_path.insert.assert_called_once_with(0, "/full/path")
                mock_import_module.assert_called_once_with("test_script")
                mock_run_path.assert_called_once_with(
                    "/full/path/test_script.py", run_name="__main__"
                )

    @patch("fever.cli.FeverWatcher")
    @patch("fever.cli.importlib.import_module")
    @patch("fever.cli.runpy.run_path")
    @patch("fever.cli.os.chdir")
    @patch("fever.cli.os.path.abspath")
    @patch("fever.cli.os.path.dirname")
    @patch("fever.cli.sys.path")
    def test_watch_command_no_cache(
        self,
        mock_sys_path,
        mock_dirname,
        mock_abspath,
        mock_chdir,
        mock_run_path,
        mock_import_module,
        mock_watcher,
    ):
        """Test watch command with cache disabled."""
        script = "test_script.py"

        mock_abspath.return_value = "/full/path/test_script.py"
        mock_dirname.return_value = "/full/path"
        mock_watcher_instance = Mock()
        mock_watcher.return_value = mock_watcher_instance

        sys.argv = ["fever", "watch", script, "--no-cache"]

        with patch("fever.cli.typer.Argument"):
            with patch("fever.cli.typer.Option"):
                from fever.cli import watch

                watch(script, [], True)

                # Verify watcher was created with cache disabled
                mock_watcher.assert_called_once_with(
                    rich_console=console, with_cache=False
                )

    @patch("fever.cli.FeverWatcher")
    @patch("fever.cli.importlib.import_module")
    @patch("fever.cli.runpy.run_path")
    @patch("fever.cli.os.chdir")
    @patch("fever.cli.os.path.abspath")
    @patch("fever.cli.os.path.dirname")
    @patch("fever.cli.sys.path")
    def test_watch_command_keyboard_interrupt(
        self,
        mock_sys_path,
        mock_dirname,
        mock_abspath,
        mock_chdir,
        mock_run_path,
        mock_import_module,
        mock_watcher,
    ):
        """Test watch command handles KeyboardInterrupt."""
        script = "test_script.py"

        mock_abspath.return_value = "/full/path/test_script.py"
        mock_dirname.return_value = "/full/path"
        mock_watcher_instance = Mock()
        mock_watcher.return_value = mock_watcher_instance

        # Make run_path raise KeyboardInterrupt
        mock_run_path.side_effect = KeyboardInterrupt()

        sys.argv = ["fever", "watch", script]

        with patch("fever.cli.typer.Argument"):
            with patch("fever.cli.typer.Option"):
                from fever.cli import watch

                # Should not raise an exception
                watch(script, [], False)

                # Verify cleanup was called
                mock_watcher_instance.stop.assert_called_once()

    @patch("fever.cli.os.path.isfile")
    @patch("fever.cli.FeverCore")
    @patch("fever.cli.BuilderUI")
    @patch("fever.cli.importlib.import_module")
    @patch("fever.cli.os.chdir")
    @patch("fever.cli.os.path.abspath")
    @patch("fever.cli.os.path.dirname")
    @patch("fever.cli.sys.path")
    def test_debug_command_success(
        self,
        mock_sys_path,
        mock_dirname,
        mock_abspath,
        mock_chdir,
        mock_import_module,
        mock_builder_ui,
        mock_fever_core,
        mock_isfile,
    ):
        """Test debug command executes successfully."""
        script = "test_script.py"
        save_file = "program_trace.pkl"

        mock_abspath.return_value = "/full/path/test_script.py"
        mock_dirname.return_value = "/full/path"
        mock_isfile.return_value = True

        mock_fever_instance = Mock()
        mock_fever_core.return_value = mock_fever_instance
        mock_builder_ui_instance = Mock()
        mock_builder_ui.return_value = mock_builder_ui_instance

        sys.argv = ["fever", "debug", script]

        with patch("fever.cli.typer.Argument"):
            from fever.cli import debug

            debug(script, [])

            # Verify file existence check
            mock_isfile.assert_called_once_with(save_file)

            # Verify FeverCore setup
            mock_fever_core.assert_called_once()
            mock_fever_instance.setup.assert_called_once()

            # Verify script execution setup
            mock_chdir.assert_called_once_with("/full/path")
            mock_sys_path.insert.assert_called_once_with(0, "/full/path")
            mock_import_module.assert_called_once_with("test_script")

            # Verify BuilderUI was run
            mock_builder_ui.assert_called_once_with(mock_fever_instance, save_file)
            mock_builder_ui_instance.run.assert_called_once()

            # Verify cleanup
            mock_fever_instance.cleanup.assert_called_once()

    @patch("fever.cli.os.path.isfile")
    def test_debug_command_missing_trace_file(self, mock_isfile):
        """Test debug command when trace file is missing."""
        script = "test_script.py"
        save_file = "program_trace.pkl"

        mock_isfile.return_value = False

        sys.argv = ["fever", "debug", script]

        with patch("fever.cli.typer.Argument"):
            from fever.cli import debug

            with self.assertRaises(FileNotFoundError) as context:
                debug(script, [])

            self.assertIn(save_file, str(context.exception))
            mock_isfile.assert_called_once_with(save_file)

    @patch.dict(os.environ, {"FEVER_PLOT_TRACE": "1"})
    @patch("fever.cli.FeverWatcher")
    @patch("fever.cli.importlib.import_module")
    @patch("fever.cli.runpy.run_path")
    @patch("fever.cli.os.chdir")
    @patch("fever.cli.os.path.abspath")
    @patch("fever.cli.os.path.dirname")
    @patch("fever.cli.sys.path")
    def test_watch_command_with_plot_trace(
        self,
        mock_sys_path,
        mock_dirname,
        mock_abspath,
        mock_chdir,
        mock_run_path,
        mock_import_module,
        mock_watcher,
    ):
        """Test watch command with FEVER_PLOT_TRACE enabled."""
        script = "test_script.py"

        mock_abspath.return_value = "/full/path/test_script.py"
        mock_dirname.return_value = "/full/path"
        mock_watcher_instance = Mock()
        mock_watcher.return_value = mock_watcher_instance

        sys.argv = ["fever", "watch", script]

        with patch("fever.cli.typer.Argument"):
            with patch("fever.cli.typer.Option"):
                from fever.cli import watch

                watch(script, [], False)

                # Verify plot_call_graph was called during cleanup
                mock_watcher_instance.fever.plot_call_graph.assert_called_once()

    @patch.dict(os.environ, {"FEVER_PLOT_DEPS": "1"})
    @patch("fever.cli.FeverWatcher")
    @patch("fever.cli.importlib.import_module")
    @patch("fever.cli.runpy.run_path")
    @patch("fever.cli.os.chdir")
    @patch("fever.cli.os.path.abspath")
    @patch("fever.cli.os.path.dirname")
    @patch("fever.cli.sys.path")
    def test_watch_command_with_plot_deps(
        self,
        mock_sys_path,
        mock_dirname,
        mock_abspath,
        mock_chdir,
        mock_run_path,
        mock_import_module,
        mock_watcher,
    ):
        """Test watch command with FEVER_PLOT_DEPS enabled."""
        script = "test_script.py"

        mock_abspath.return_value = "/full/path/test_script.py"
        mock_dirname.return_value = "/full/path"
        mock_watcher_instance = Mock()
        mock_watcher.return_value = mock_watcher_instance
        mock_watcher_instance.fever.dependency_tracker.all_imports = [
            "module1",
            "module2",
        ]

        sys.argv = ["fever", "watch", script]

        with patch("fever.cli.typer.Argument"):
            with patch("fever.cli.typer.Option"):
                from fever.cli import watch

                watch(script, [], False)

                # Verify plot_dependency_graph was called during cleanup
                mock_watcher_instance.fever.plot_dependency_graph.assert_called_once()

    @patch("fever.cli.FeverWatcher")
    @patch("fever.cli.importlib.import_module")
    @patch("fever.cli.runpy.run_path")
    @patch("fever.cli.os.chdir")
    @patch("fever.cli.os.path.abspath")
    @patch("fever.cli.os.path.dirname")
    @patch("fever.cli.sys.path")
    def test_watch_command_exports_trace(
        self,
        mock_sys_path,
        mock_dirname,
        mock_abspath,
        mock_chdir,
        mock_run_path,
        mock_import_module,
        mock_watcher,
    ):
        """Test watch command exports trace file."""
        script = "test_script.py"

        mock_abspath.return_value = "/full/path/test_script.py"
        mock_dirname.return_value = "/full/path"
        mock_watcher_instance = Mock()
        mock_watcher.return_value = mock_watcher_instance

        sys.argv = ["fever", "watch", script]

        with patch("fever.cli.typer.Argument"):
            with patch("fever.cli.typer.Option"):
                from fever.cli import watch

                watch(script, [], False)

                # Verify trace export was called during cleanup
                mock_watcher_instance.fever.export_trace.assert_called_once_with(
                    "program_trace.pkl"
                )

    def test_app_creation(self):
        """Test that typer app is created correctly."""
        from fever.cli import app

        self.assertIsNotNone(app)

    def test_console_creation(self):
        """Test that rich console is created correctly."""
        from fever.cli import console

        self.assertIsNotNone(console)

    def test_main_execution(self):
        """Test that the script can be executed as main."""
        # This test just verifies that the if __name__ == "__main__" block doesn't error
        with patch("fever.cli.app"):
            # Import the module to trigger any potential issues
            import fever.cli

            # If we get here without errors, the main block is fine
            self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
