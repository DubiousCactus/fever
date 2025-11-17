#
# Copyright © 2025-10-07 22:38:27 Théo Morales <theo.morales.fr@gmail.com>
#
# Distributed under terms of the MIT license.

from typing import Any, Dict, Tuple

from .types import (
    FeverParameters,
)


class Cache:
    def __init__(
        self, min_calls_threshold: int = 2, min_time_threhsold: float = 1.0
    ) -> None:
        self._entries: dict[Tuple[object, int], Any] = {}
        self._stats: dict[Tuple[object, int], Dict[str, Any]] = {}
        self._min_calls_threshold = min_calls_threshold
        self._min_time_threhsold = min_time_threhsold

    def get(self, function: object, params: FeverParameters) -> Any | None:
        return self._entries.get((function, params.hash), None)

    def set(
        self,
        function: object,
        params: FeverParameters,
        statistics: Dict[str, Any],
        result: Any,
    ) -> None:
        if (
            statistics.get("calls", 0) >= self._min_calls_threshold
            or statistics.get("weight", 0) >= self._min_time_threhsold
        ):
            self._entries[(function, params.hash)] = result
            self._stats[(function, params.hash)] = statistics
