from __future__ import annotations
from typing import Dict
import logging

from .voltage_tiers import VoltageTier
from .material import Material
from .recipe_options import RecipeOptions

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class RawRecipe:
    eu_per_tick: float
    processing_time: float  # in seconds
    amperage: int
    voltage_tier: int
    inputs: Dict[Material, float]
    output_specifications: Dict[int, tuple[Material, float, float]]
    recipe_options: RecipeOptions

    def __init__(
        self,
        eu_per_tick: float,
        processing_time: float,
        amperage: int,
        voltage_tier: int,
        inputs: Dict[Material, float],
        output_specifications: Dict[int, tuple[Material, float, float]],
        recipe_options: RecipeOptions
    ):
        self.eu_per_tick = eu_per_tick
        self.processing_time = processing_time
        self.amperage = amperage
        self.voltage_tier = voltage_tier
        self.inputs = inputs
        self.output_specifications = output_specifications
        self.recipe_options = recipe_options

    def __repr__(self) -> str:
        return (f'RawRecipe(inputs={self.inputs}, outputs={self.output_specifications}, '
                f'eu_per_tick={self.eu_per_tick}, processing_time={self.processing_time}, '
                f'amperage={self.amperage}, voltage_tier={self.voltage_tier}, '
                f'recipe_options={self.recipe_options})')

    @property
    def total_eu(self) -> float:
        return self.eu_per_tick * self.processing_time * 20
