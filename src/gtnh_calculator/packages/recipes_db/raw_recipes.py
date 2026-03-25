from __future__ import annotations
from typing import Dict
import logging
from collections import Counter

from .voltage_tiers import VoltageTier
from .material import Material, MaterialGroup
from .machines import Machine
from .recipe_options import RecipeOptions

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class RawRecipe:
    voltage: float
    amperage: float
    processing_time: float  # in seconds
    inputs: Dict[MaterialGroup, float]
    outputs: Dict[Material, float]
    output_probabilities: [Material, float]
    valid_machines: list[Machine]
    recipe_special_value: float
    metadata: Dict[str, float]
    recipe_options: RecipeOptions

    def __init__(
        self,
        voltage: float,
        amperage: float,
        processing_time: float,
        inputs: Dict[MaterialGroup, float],
        outputs: Dict[Material, float],
        output_probabilities: [Material, float],
        valid_machines: list[Machine],
        recipe_special_value: float,
        metadata: Dict[str, float],
        recipe_options: RecipeOptions
    ):
        self.voltage = voltage
        self.amperage = amperage
        self.processing_time = processing_time
        self.inputs = inputs
        self.outputs = outputs
        self.output_probabilities = output_probabilities
        self.valid_machines = valid_machines
        self.recipe_special_value = recipe_special_value
        self.metadata = metadata
        self.recipe_options = recipe_options

    def __repr__(self) -> str:
        return (f'RawRecipe(inputs={self.inputs}, outputs={self.outputs}, processing_time={self.processing_time}, '
                f'recipe_options={self.recipe_options})')

    @property
    def total_eu(self) -> float:
        return self.eu_per_tick * self.processing_time * 20

    @property
    def eu_per_tick(self) -> float:
        if self.processing_time <= 0:
            return 0
        return self.voltage * self.amperage

    @property
    def voltage_tier(self) -> int:
        return VoltageTier.voltage_tier_by_eu(abs(self.eu_per_tick))
