import unittest
from unittest.mock import Mock, patch
import os
from typing import Optional

from fever.utils import parse_verbosity, ConsoleInterface
from rich.console import Console


class TestParseVerbosity(unittest.TestCase):
    def test_parse_verbosity_default(self):
        """Test parse_verbosity with default (no environment variable)."""
        with patch.dict(os.environ, {}, clear=True):
            result = parse_verbosity()
            self.assertEqual(result, 0)

    def test_parse_verbosity_v1(self):
        """Test parse_verbosity with verbosity level 1."""
        with patch.dict(os.environ, {"FEVER_VERBOSITY": "v"}):
            result = parse_verbosity()
            self.assertEqual(result, 1)

        with patch.dict(os.environ, {"FEVER_VERBOSITY": "1"}):
            result = parse_verbosity()
            self.assertEqual(result, 1)

    def test_parse_verbosity_v2(self):
        """Test parse_verbosity with verbosity level 2."""
        with patch.dict(os.environ, {"FEVER_VERBOSITY": "vv"}):
            result = parse_verbosity()
            self.assertEqual(result, 2)

        with patch.dict(os.environ, {"FEVER_VERBOSITY": "2"}):
            result = parse_verbosity()
            self.assertEqual(result, 2)

    def test_parse_verbosity_v3(self):
        """Test parse_verbosity with verbosity level 3."""
        with patch.dict(os.environ, {"FEVER_VERBOSITY": "vvv"}):
            result = parse_verbosity()
            self.assertEqual(result, 3)

        with patch.dict(os.environ, {"FEVER_VERBOSITY": "3"}):
            result = parse_verbosity()
            self.assertEqual(result, 3)

    def test_parse_verbosity_v4(self):
        """Test parse_verbosity with verbosity level 4."""
        with patch.dict(os.environ, {"FEVER_VERBOSITY": "vvvv"}):
            result = parse_verbosity()
            self.assertEqual(result, 4)

        with patch.dict(os.environ, {"FEVER_VERBOSITY": "4"}):
            result = parse_verbosity()
            self.assertEqual(result, 4)

    def test_parse_verbosity_case_insensitive(self):
        """Test parse_verbosity is case insensitive."""
        with patch.dict(os.environ, {"FEVER_VERBOSITY": "V"}):
            result = parse_verbosity()
            self.assertEqual(result, 1)

        with patch.dict(os.environ, {"FEVER_VERBOSITY": "VV"}):
            result = parse_verbosity()
            self.assertEqual(result, 2)

    def test_parse_verbosity_invalid(self):
        """Test parse_verbosity with invalid values."""
        with patch.dict(os.environ, {"FEVER_VERBOSITY": "invalid"}):
            result = parse_verbosity()
            self.assertEqual(result, 0)

        with patch.dict(os.environ, {"FEVER_VERBOSITY": "5"}):
            result = parse_verbosity()
            self.assertEqual(result, 0)


class TestConsoleInterface(unittest.TestCase):
    def test_init_with_console(self):
        """Test ConsoleInterface initialization with console."""
        mock_console = Mock(spec=Console)
        console_if = ConsoleInterface(mock_console)

        self.assertEqual(console_if.console, mock_console)
        self.assertEqual(console_if._print, mock_console.print)

    def test_init_without_console(self):
        """Test ConsoleInterface initialization without console."""
        console_if = ConsoleInterface(None)

        self.assertIsNone(console_if.console)
        # _print should be a no-op function
        self.assertIsNone(console_if._print(None))

    def test_print_with_console(self):
        """Test print method with console."""
        mock_console = Mock(spec=Console)
        console_if = ConsoleInterface(mock_console)

        console_if.print("test message", style="red")

        mock_console.print.assert_called_once_with("test message", style="red")

    def test_print_without_console(self):
        """Test print method without console (no-op)."""
        console_if = ConsoleInterface(None)

        # Should not raise any errors
        console_if.print("test message", style="red")

        # Since _print is a no-op, we can't easily verify it was called
        # but the fact that no exception is raised is the test

    def test_print_with_multiple_args(self):
        """Test print method with multiple arguments."""
        mock_console = Mock(spec=Console)
        console_if = ConsoleInterface(mock_console)

        console_if.print("arg1", "arg2", kwarg1="value1")

        mock_console.print.assert_called_once_with("arg1", "arg2", kwarg1="value1")

    def test_print_with_kwargs(self):
        """Test print method with keyword arguments."""
        mock_console = Mock(spec=Console)
        console_if = ConsoleInterface(mock_console)

        console_if.print("test", style="bold", highlight=True)

        mock_console.print.assert_called_once_with("test", style="bold", highlight=True)


if __name__ == "__main__":
    unittest.main()
