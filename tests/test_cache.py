import unittest
from unittest.mock import Mock, patch
from collections import defaultdict

from fever.cache import (
    Cache,
    ParamWiseLRUEvictionPolicy,
    EvictionPolicy,
    parse_mem_limit,
)
from fever.types import FeverParameters
from fever.utils import ConsoleInterface


class TestParseMemLimit(unittest.TestCase):
    def test_parse_kb(self):
        """Test parsing KB memory limit."""
        self.assertEqual(parse_mem_limit("50KB"), 50 * 1024)
        self.assertEqual(parse_mem_limit("100kb"), 100 * 1024)

    def test_parse_mb(self):
        """Test parsing MB memory limit."""
        self.assertEqual(parse_mem_limit("10MB"), 10 * 1024 * 1024)
        self.assertEqual(parse_mem_limit("5mb"), 5 * 1024 * 1024)

    def test_parse_gb(self):
        """Test parsing GB memory limit."""
        self.assertEqual(parse_mem_limit("2GB"), 2 * 1024 * 1024 * 1024)
        self.assertEqual(parse_mem_limit("1gb"), 1 * 1024 * 1024 * 1024)

    def test_parse_bytes(self):
        """Test parsing raw bytes."""
        self.assertEqual(parse_mem_limit("1024"), 1024)
        self.assertEqual(parse_mem_limit("2048"), 2048)


class TestParamWiseLRUEvictionPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = ParamWiseLRUEvictionPolicy()

    def test_init(self):
        """Test policy initialization."""
        self.assertIsInstance(self.policy._calls, defaultdict)
        self.assertEqual(self.policy._decay_factor, 0.9)

    def test_update_all(self):
        """Test updating all entries with decay."""
        # Add some test data
        self.policy._calls["func1"]["params1"] = 10.0
        self.policy._calls["func1"]["params2"] = 5.0
        self.policy._calls["func2"]["params1"] = 3.0

        self.policy.update_all()

        # Check that all values were decayed
        self.assertAlmostEqual(self.policy._calls["func1"]["params1"], 9.0)
        self.assertAlmostEqual(self.policy._calls["func1"]["params2"], 4.5)
        self.assertAlmostEqual(self.policy._calls["func2"]["params1"], 2.7)

    def test_update_entry_new(self):
        """Test updating a new entry."""
        self.policy.update_entry("func1", "params1")

        self.assertEqual(self.policy._calls["func1"]["params1"], 1.0)

    def test_update_entry_existing(self):
        """Test updating an existing entry."""
        self.policy._calls["func1"]["params1"] = 5.0

        self.policy.update_entry("func1", "params1")

        self.assertEqual(self.policy._calls["func1"]["params1"], 6.0)

    def test_pick_with_timestamp(self):
        """Test picking entry to evict based on timestamp."""
        entries = {"func1": {"params1": "result1"}, "func2": {"params1": "result2"}}
        stats = {
            "func1": {"params1": {"timestamp": 100.0}},
            "func2": {"params1": {"timestamp": 200.0}},
        }

        result = self.policy.pick(entries, stats, 1024)

        # Should pick the entry with the oldest timestamp
        self.assertEqual(result, ("func1", "params1"))

    def test_pick_with_score(self):
        """Test picking entry to evict based on score when no timestamps."""
        entries = {"func1": {"params1": "result1"}, "func2": {"params1": "result2"}}
        stats = {
            "func1": {"params1": {"weight": 0.5}},
            "func2": {"params1": {"weight": 0.2}},
        }
        # Set up calls to affect score
        self.policy._calls["func1"]["params1"] = 10.0
        self.policy._calls["func2"]["params1"] = 5.0

        result = self.policy.pick(entries, stats, 1024)

        # Should pick the entry with the lowest score (weight * calls)
        self.assertEqual(result, ("func2", "params1"))


class TestCache(unittest.TestCase):
    def setUp(self):
        self.console = Mock(spec=ConsoleInterface)
        self.eviction_policy = Mock(spec=EvictionPolicy)
        self.cache = Cache(
            console=self.console,
            mem_limit="50KB",
            eviction_policy=self.eviction_policy,
            min_calls_threshold=2,
            min_time_s_threhsold=0.1,
            enabled=True,
        )

    def test_init(self):
        """Test cache initialization."""
        self.assertEqual(self.cache.mem_limit_human, "50KB")
        self.assertEqual(self.cache._mem_limit_bytes, 50 * 1024)
        self.assertEqual(self.cache._min_calls_threshold, 2)
        self.assertEqual(self.cache._min_time_threhsold, 0.1)
        self.assertTrue(self.cache._enabled)

    def test_init_disabled(self):
        """Test cache initialization when disabled."""
        cache = Cache(
            console=self.console,
            mem_limit="50KB",
            eviction_policy=self.eviction_policy,
            enabled=False,
        )
        self.assertFalse(cache._enabled)

    def test_get_disabled(self):
        """Test get when cache is disabled."""
        self.cache._enabled = False

        result = self.cache.get(Mock(), Mock())

        self.assertIsNone(result)
        # Should not call eviction policy
        self.eviction_policy.update_all.assert_not_called()

    def test_get_miss(self):
        """Test get when entry is not found."""
        function = Mock()
        params = Mock(spec=FeverParameters)
        params.hash = "test_hash"

        result = self.cache.get(function, params)

        self.assertIsNone(result)
        self.eviction_policy.update_all.assert_called_once()

    def test_get_hit(self):
        """Test get when entry is found."""
        function = Mock()
        params = Mock(spec=FeverParameters)
        params.hash = "test_hash"

        # Set up cache entry
        self.cache._entries[function][params.hash] = "test_result"

        result = self.cache.get(function, params)

        self.assertEqual(result, "test_result")
        self.eviction_policy.update_all.assert_called_once()
        self.eviction_policy.update_entry.assert_called_once_with(function, params.hash)

    def test_set_disabled(self):
        """Test set when cache is disabled."""
        self.cache._enabled = False

        self.cache.set(Mock(), Mock(), {}, "result")

        # Should not add anything to cache
        self.assertEqual(len(self.cache._entries), 0)

    def test_set_below_thresholds(self):
        """Test set when statistics are below thresholds."""
        function = Mock()
        params = Mock(spec=FeverParameters)
        params.hash = "test_hash"
        statistics = {"calls": 1, "weight": 0.05}  # Below both thresholds

        self.cache.set(function, params, statistics, "result")

        # Should not add to cache
        self.assertNotIn(params.hash, self.cache._entries[function])

    def test_set_above_thresholds(self):
        """Test set when statistics are above thresholds."""
        function = Mock()
        params = Mock(spec=FeverParameters)
        params.hash = "test_hash"
        statistics = {"calls": 5, "weight": 0.2}  # Above both thresholds

        self.cache.set(function, params, statistics, "result")

        # Should add to cache
        self.assertEqual(self.cache._entries[function][params.hash], "result")
        self.assertEqual(self.cache._stats[function][params.hash], statistics)
        self.eviction_policy.update_entry.assert_called_once_with(function, params.hash)

    def test_set_memory_limit_exceeded(self):
        """Test set when memory limit is exceeded."""
        function = Mock()
        params = Mock(spec=FeverParameters)
        params.hash = "test_hash"
        statistics = {"calls": 5, "weight": 0.2}

        # Mock pympler to simulate memory limit exceeded
        with patch("fever.cache.asizeof") as mock_asizeof:
            mock_asizeof.asizeof.return_value = 100 * 1024  # Exceeds 50KB limit

            # Mock eviction policy pick
            self.eviction_policy.pick.return_value = (function, params.hash)

            self.cache.set(function, params, statistics, "result")

            # Should attempt eviction
            self.console.print.assert_called()
            self.eviction_policy.pick.assert_called()

    def test_linearize(self):
        """Test linearize method (placeholder)."""
        # This method is currently a placeholder
        self.cache.linearize()
        # Should not raise any errors


if __name__ == "__main__":
    unittest.main()
