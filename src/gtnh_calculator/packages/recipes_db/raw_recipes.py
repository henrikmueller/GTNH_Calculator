from __future__ import annotations
from dataclasses import dataclass
from frozendict import frozendict
import logging
from collections import defaultdict

from .material import Material, MaterialGroup
from .recipe_options import RecipeOptions

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


type InputCombination = frozendict[MaterialGroup, Material]


def get_output_dict(output_specifications: frozendict[int, tuple[Material, float, float]]) -> frozendict[Material, float]:
    # TODO: Take number of output slots into account (e.g. for plant mass)
    result = defaultdict(float)
    for m, a, p in output_specifications.values():
        result[m] += a * p
    return frozendict(result)


@dataclass(frozen=True)
class RawRecipe:
    category: str
    eu_per_tick: float
    processing_time: float  # in seconds
    amperage: int
    voltage_tier: int
    inputs: frozendict[MaterialGroup, float]
    output_specifications: frozendict[int, tuple[Material, float, float]]
    recipe_options: RecipeOptions

    def __repr__(self) -> str:
        return (f'RawRecipe(inputs={self.inputs}, output_specifications={self.output_specifications}, '
                f'eu_per_tick={self.eu_per_tick}, processing_time={self.processing_time}, '
                f'amperage={self.amperage}, voltage_tier={self.voltage_tier}, '
                f'recipe_options={self.recipe_options})')

    @property
    def total_eu(self) -> float:
        return self.eu_per_tick * self.processing_time * 20

    @property
    def output_dict(self) -> frozendict[Material, float]:
        return get_output_dict(self.output_specifications)
