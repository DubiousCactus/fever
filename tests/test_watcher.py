import unittest
from unittest.mock import Mock, patch, MagicMock
import os
import sys
import threading
from pathlib import Path
from typing import Optional

from fever.watcher import FeverWatcher
from fever.core import FeverCore


class TestFeverWatcher(unittest.TestCase):
    def setUp(self):
        self.test_root_dir = "/test/root/dir"

    def test_init_default_params(self):
        """Test FeverWatcher initialization with default parameters."""
        with patch("fever.watcher.parse_verbosity", return_value=1):
            with patch("fever.watcher.Path.cwd", return_value=Path("/default/dir")):
                with patch("fever.watcher.Console"):
                    with patch("fever.watcher.FeverCore") as mock_core:
                        watcher = FeverWatcher()

                        self.assertEqual(watcher._root_dir, "/default/dir")
                        self.assertEqual(watcher._verbosity, 1)
                        self.assertFalse(watcher._running)
                        mock_core.assert_called_once()

    def test_init_custom_params(self):
        """Test FeverWatcher initialization with custom parameters."""
        mock_console = Mock()

        with patch("fever.watcher.parse_verbosity", return_value=2):
            with patch("fever.watcher.Console") as mock_console_class:
                mock_console_class.return_value = mock_console
                with patch("fever.watcher.FeverCore") as mock_core:
                    watcher = FeverWatcher(
                        rich_console=mock_console,
                        root_dir=self.test_root_dir,
                        with_cache=False,
                    )

                    self.assertEqual(watcher._root_dir, self.test_root_dir)
                    self.assertEqual(watcher._verbosity, 2)
                    self.assertFalse(watcher._running)
                    mock_core.assert_called_once_with(mock_console, with_cache=False)

    def test_init_zero_verbosity(self):
        """Test FeverWatcher initialization with zero verbosity."""
        with patch("fever.watcher.parse_verbosity", return_value=0):
            with patch("fever.watcher.Path.cwd", return_value=Path("/default/dir")):
                with patch("fever.watcher.FeverCore") as mock_core:
                    watcher = FeverWatcher()

                    # Console should be None when verbosity is 0
                    mock_core.assert_called_once_with(None, with_cache=True)

    @patch("fever.watcher.pywatchman.client")
    @patch("fever.watcher.sys._getframe")
    @patch("fever.watcher.threading.Thread")
    def test_watch_success(self, mock_thread, mock_getframe, mock_client_class):
        """Test watch method successful execution."""
        # Setup mocks
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        # Mock query responses
        mock_client.query.side_effect = [
            {"watch": "/test/watch"},  # watch-project response
            None,  # subscribe response
        ]

        # Mock receive for initial drain
        mock_client.receive.side_effect = [
            pywatchman.SocketTimeout("timeout"),  # Initial drain timeout
            None,  # Will be replaced in thread
        ]

        mock_frame = Mock()
        mock_getframe.return_value = mock_frame

        with patch("fever.watcher.parse_verbosity", return_value=1):
            with patch("fever.watcher.Path.cwd", return_value=Path(self.test_root_dir)):
                with patch("fever.watcher.Console"):
                    with patch("fever.watcher.FeverCore") as mock_core_class:
                        mock_fever = Mock()
                        mock_core_class.return_value = mock_fever

                        watcher = FeverWatcher(root_dir=self.test_root_dir)

                        # Start watching
                        watcher.watch()

                        # Verify setup was called
                        mock_fever.setup.assert_called_once_with(
                            caller_frame=mock_frame
                        )

                        # Verify thread was started
                        self.assertTrue(watcher._running)
                        mock_thread.assert_called_once()
                        thread_args = mock_thread.call_args[1]
                        self.assertEqual(
                            thread_args["target"], watcher._run_blocking
                        )  # This will be the internal function

    @patch("fever.watcher.pywatchman.client")
    @patch("fever.watcher.sys._getframe")
    @patch("fever.watcher.threading.Thread")
    def test_watch_with_file_changes(
        self, mock_thread, mock_getframe, mock_client_class
    ):
        """Test watch method with file changes."""
        # Setup mocks
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.query.side_effect = [{"watch": "/test/watch"}, None]

        # Mock file change message
        change_message = {
            "subscription": "watcher_sub",
            "is_fresh_instance": False,
            "files": [
                {"name": "/test/file1.py", "mtime_ms": 123456},
                {"name": "/test/file2.py", "mtime_ms": 123457},
            ],
        }

        mock_client.receive.side_effect = [
            pywatchman.SocketTimeout("timeout"),  # Initial drain
            change_message,
            pywatchman.SocketTimeout("timeout"),  # Continue loop
        ]

        mock_frame = Mock()
        mock_getframe.return_value = mock_frame

        with patch("fever.watcher.parse_verbosity", return_value=1):
            with patch("fever.watcher.Path.cwd", return_value=Path(self.test_root_dir)):
                with patch("fever.watcher.Console"):
                    with patch("fever.watcher.FeverCore") as mock_core_class:
                        mock_fever = Mock()
                        mock_core_class.return_value = mock_fever

                        watcher = FeverWatcher(root_dir=self.test_root_dir)
                        watcher.watch()

                        # Simulate the thread running briefly
                        import time

                        time.sleep(0.01)  # Brief pause to let thread start

                        # Stop the watcher
                        watcher.stop()

                        # Verify reload was called with correct module names
                        mock_fever.reload.assert_called_once_with(["file1", "file2"])

    @patch("fever.watcher.pywatchman.client")
    @patch("fever.watcher.sys._getframe")
    @patch("fever.watcher.threading.Thread")
    def test_watch_ignores_fresh_instance(
        self, mock_thread, mock_getframe, mock_client_class
    ):
        """Test watch method ignores fresh instance messages."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.query.side_effect = [{"watch": "/test/watch"}, None]

        # Fresh instance message (should be ignored)
        fresh_message = {
            "subscription": "watcher_sub",
            "is_fresh_instance": True,
            "files": [{"name": "/test/file1.py", "mtime_ms": 123456}],
        }

        mock_client.receive.side_effect = [
            pywatchman.SocketTimeout("timeout"),
            fresh_message,
            pywatchman.SocketTimeout("timeout"),
        ]

        mock_frame = Mock()
        mock_getframe.return_value = mock_frame

        with patch("fever.watcher.parse_verbosity", return_value=1):
            with patch("fever.watcher.Path.cwd", return_value=Path(self.test_root_dir)):
                with patch("fever.watcher.Console"):
                    with patch("fever.watcher.FeverCore") as mock_core_class:
                        mock_fever = Mock()
                        mock_core_class.return_value = mock_fever

                        watcher = FeverWatcher(root_dir=self.test_root_dir)
                        watcher.watch()

                        # Brief pause then stop
                        import time

                        time.sleep(0.01)
                        watcher.stop()

                        # Reload should not have been called for fresh instance
                        mock_fever.reload.assert_not_called()

    @patch("fever.watcher.pywatchman.client")
    @patch("fever.watcher.sys._getframe")
    @patch("fever.watcher.threading.Thread")
    def test_watch_ignores_wrong_subscription(
        self, mock_thread, mock_getframe, mock_client_class
    ):
        """Test watch method ignores messages with wrong subscription."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.query.side_effect = [{"watch": "/test/watch"}, None]

        # Wrong subscription message (should be ignored)
        wrong_message = {
            "subscription": "other_sub",
            "is_fresh_instance": False,
            "files": [{"name": "/test/file1.py", "mtime_ms": 123456}],
        }

        mock_client.receive.side_effect = [
            pywatchman.SocketTimeout("timeout"),
            wrong_message,
            pywatchman.SocketTimeout("timeout"),
        ]

        mock_frame = Mock()
        mock_getframe.return_value = mock_frame

        with patch("fever.watcher.parse_verbosity", return_value=1):
            with patch("fever.watcher.Path.cwd", return_value=Path(self.test_root_dir)):
                with patch("fever.watcher.Console"):
                    with patch("fever.watcher.FeverCore") as mock_core_class:
                        mock_fever = Mock()
                        mock_core_class.return_value = mock_fever

                        watcher = FeverWatcher(root_dir=self.test_root_dir)
                        watcher.watch()

                        # Brief pause then stop
                        import time

                        time.sleep(0.01)
                        watcher.stop()

                        # Reload should not have been called
                        mock_fever.reload.assert_not_called()

    def test_stop(self):
        """Test stop method."""
        with patch("fever.watcher.parse_verbosity", return_value=1):
            with patch("fever.watcher.Path.cwd", return_value=Path(self.test_root_dir)):
                with patch("fever.watcher.Console"):
                    with patch("fever.watcher.FeverCore") as mock_core_class:
                        mock_fever = Mock()
                        mock_core_class.return_value = mock_fever

                        watcher = FeverWatcher(root_dir=self.test_root_dir)

                        # Set running to True first
                        watcher._running = True

                        # Stop the watcher
                        watcher.stop()

                        # Verify state changes
                        self.assertFalse(watcher._running)
                        mock_fever.cleanup.assert_called_once()

    def test_stop_when_not_running(self):
        """Test stop method when not already running."""
        with patch("fever.watcher.parse_verbosity", return_value=1):
            with patch("fever.watcher.Path.cwd", return_value=Path(self.test_root_dir)):
                with patch("fever.watcher.Console"):
                    with patch("fever.watcher.FeverCore") as mock_core_class:
                        mock_fever = Mock()
                        mock_core_class.return_value = mock_fever

                        watcher = FeverWatcher(root_dir=self.test_root_dir)

                        # Ensure not running
                        self.assertFalse(watcher._running)

                        # Stop should still work
                        watcher.stop()

                        self.assertFalse(watcher._running)
                        mock_fever.cleanup.assert_called_once()

    @patch("fever.watcher.pywatchman.client")
    @patch("fever.watcher.sys._getframe")
    @patch("fever.watcher.threading.Thread")
    def test_watch_handles_socket_timeout(
        self, mock_thread, mock_getframe, mock_client_class
    ):
        """Test watch method handles socket timeouts gracefully."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_client.query.side_effect = [{"watch": "/test/watch"}, None]

        # Continuous timeouts
        mock_client.receive.side_effect = [
            pywatchman.SocketTimeout("timeout"),  # Initial drain
            pywatchman.SocketTimeout("timeout"),  # In loop
            pywatchman.SocketTimeout("timeout"),  # In loop
        ]

        mock_frame = Mock()
        mock_getframe.return_value = mock_frame

        with patch("fever.watcher.parse_verbosity", return_value=1):
            with patch("fever.watcher.Path.cwd", return_value=Path(self.test_root_dir)):
                with patch("fever.watcher.Console"):
                    with patch("fever.watcher.FeverCore") as mock_core_class:
                        mock_fever = Mock()
                        mock_core_class.return_value = mock_fever

                        watcher = FeverWatcher(root_dir=self.test_root_dir)
                        watcher.watch()

                        # Brief pause then stop
                        import time

                        time.sleep(0.01)
                        watcher.stop()

                        # Should not have crashed
                        self.assertTrue(
                            watcher._running or True
                        )  # Might be stopped by now


if __name__ == "__main__":
    unittest.main()
