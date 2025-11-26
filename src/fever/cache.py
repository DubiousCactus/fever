#
# Copyright © 2025-10-07 22:38:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

import abc
from collections import defaultdict
from typing import Any, Dict, Tuple

from pympler import asizeof

from fever.utils import ConsoleInterface

from .types import (
    FeverParameters,
)


def parse_mem_limit(mem_limit: str) -> int:
    if mem_limit.lower().endswith("kb"):
        return int(mem_limit[:-2]) * 1024
    elif mem_limit.lower().endswith("mb"):
        return int(mem_limit[:-2]) * 1024 * 1024
    elif mem_limit.lower().endswith("gb"):
        return int(mem_limit[:-2]) * 1024 * 1024 * 1024
    else:
        return int(mem_limit)


class EvictionPolicy(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def update_all(self) -> None:
        """
        Update the internal state of the eviction policy.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def update_entry(self, function_key: object, params_key: int) -> None:
        """
        Update the internal state of the eviction policy.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def pick(
        self,
        entries: Dict[object, Dict[int, Any]],
        stats: Dict[object, Dict[int, Any]],
        mem_limit_bytes: int,
    ) -> Tuple[object, int]:
        """
        Pick an entry to evict from the cache.
        Args:
            entries: The current cache entries.
            stats: The statistics associated with each cache entry.
            mem_limit_bytes: The memory limit in bytes.
        """
        raise NotImplementedError


class ParamWiseLRUEvictionPolicy(EvictionPolicy):
    """
    Eviction policy that evicts the least recently used entry based on the parameters
    passed to the function. For entries with only one parameter combination per
    function, evict the entry with the lowest (time spent * calls), with decayed call counts.
    This gives a balance between frequency of use and cost of recomputation.
    """

    def __init__(self) -> None:
        self._calls: Dict[object, Dict[int, float]] = defaultdict(dict)
        self._decay_factor = 0.9

    def update_all(self) -> None:
        for function in self._calls.keys():
            for params in self._calls[function].keys():
                self._calls[function][params] *= self._decay_factor

    def update_entry(self, function_key: object, params_key: int) -> None:
        if params_key not in self._calls[function_key]:
            self._calls[function_key][params_key] = 1.0
        else:
            self._calls[function_key][params_key] += 1.0

    def pick(
        self,
        entries: Dict[object, Dict[int, Any]],
        stats: Dict[object, Dict[int, Any]],
        mem_limit_bytes: int,
    ) -> Tuple[object, int]:
        # INFO: For function calls with multiple cache entries, evict the oldest entry.
        # Otherwise evict the entry with the lowest (time spent * calls). But decay the
        # calls such that old entries are preferred for eviction.
        candidate, oldest_ts = None, float("+inf")
        for fn_key in entries.keys():
            assert fn_key in stats
            for param_key in entries[fn_key].keys():
                assert param_key in stats[fn_key]
                ts = stats[fn_key][param_key].get("timestamp", float("+inf"))
                if ts > oldest_ts:
                    oldest_ts = ts
                    candidate = (fn_key, param_key)
        if candidate is not None:
            return candidate

        min_score, candidate = float("+inf"), None
        for fn_key in entries.keys():
            assert fn_key in stats
            for param_key in entries[fn_key].keys():
                assert param_key in stats[fn_key]
                weight = stats[fn_key][param_key].get("weight", 0)
                score = weight * self._calls[fn_key].get(param_key, 1)
                if score < min_score:
                    min_score = score
                    candidate = (fn_key, param_key)
        assert candidate is not None
        return candidate


class Cache:
    def __init__(
        self,
        console: ConsoleInterface,
        mem_limit: str,
        eviction_policy: EvictionPolicy,
        min_calls_threshold: int = 2,
        min_time_s_threhsold: float = 0.1,
        enabled: bool = True
    ) -> None:
        self._console = console
        self._entries: Dict[object, Dict[int, Any]] = defaultdict(dict)
        self._stats: Dict[object, Dict[int, Any]] = defaultdict(dict)
        self.mem_limit_human = mem_limit
        self._mem_limit_bytes = parse_mem_limit(mem_limit)
        self._min_calls_threshold = min_calls_threshold
        self._min_time_threhsold = min_time_s_threhsold
        self._eviction_policy = eviction_policy
        self._enabled = enabled

    def get(self, function: object, params: FeverParameters) -> Any | None:
        if not self._enabled:
            return None
        self._eviction_policy.update_all()
        if function_cache := self._entries.get(function, None):
            if entry := function_cache.get(params.hash, None):
                self._eviction_policy.update_entry(function, params.hash)
                return entry
        return None

    def set(
        self,
        function: object,
        params: FeverParameters,
        statistics: Dict[str, Any],
        result: Any,
    ) -> None:
        if not self._enabled:
            return 
        if (
            statistics.get("calls", 0) >= self._min_calls_threshold
            and statistics.get("weight", 0) >= self._min_time_threhsold
        ):
            self._entries[function][params.hash] = result
            self._stats[function][params.hash] = statistics
            self._eviction_policy.update_entry(function, params.hash)
            if asizeof.asizeof(self._entries) > self._mem_limit_bytes:
                self._console.print(
                    f"Cache exceeded memory limit of {self.mem_limit_human}; evicting entries...",
                    style="bold red",
                )
                while asizeof.asizeof(self._entries) > self._mem_limit_bytes:
                    fn_key, params_key = self._eviction_policy.pick(
                        self._entries, self._stats, self._mem_limit_bytes
                    )
                    del self._entries[fn_key][params_key]
                    del self._stats[fn_key][params_key]

    def linearize(self) -> None:
        """
        Linearize the cache by aggregating entries along linear call paths.
        """
        # TODO: Topological sort of the call graph. Then we can do more advanced things.
        # NOTE: Is this useful?
        pass
