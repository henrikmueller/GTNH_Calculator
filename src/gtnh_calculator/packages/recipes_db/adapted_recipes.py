from __future__ import annotations
from dataclasses import dataclass
from frozendict import frozendict
import logging

from .material import Material, MaterialGroup

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass(frozen=True)
class AdaptedRecipe:
    eu_per_tick: float
    processing_time: float  # in seconds
    amperage: int
    inputs: frozendict[MaterialGroup, float]
    output_specifications: frozendict[int, tuple[Material, float, float]]
    used_parallels: int = 1

    def __repr__(self) -> str:
        return (f'AdaptedRecipe(inputs={self.inputs}, outputs={self.output_specifications}, '
                f'eu_per_tick={self.eu_per_tick}, processing_time={self.processing_time}, '
                f'amperage={self.amperage}, used_parallels={self.used_parallels})')

    @property
    def total_eu(self) -> float:
        return self.eu_per_tick * self.processing_time * 20
