from __future__ import annotations
from typing import Dict
import logging

from .voltage_tiers import VoltageTier
from .material import Material
from .recipe_options.recipe_options import RecipeOptions

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class RawRecipe:
    materials: Dict[Material, float]
    processing_time: float  # in seconds
    recipe_options: RecipeOptions
    chance_based: list[Material]

    def __init__(
            self,
            materials: Dict[Material, float],
            processing_time: float,
            recipe_options: RecipeOptions,
            chance_based: list[Material]
    ):
        self.materials = materials
        self.processing_time = processing_time
        self.recipe_options = recipe_options
        self.chance_based = chance_based

    def __repr__(self) -> str:
        return (f'RawRecipe(materials={self.materials}, processing_time={self.processing_time}, '
                f'recipe_options={self.recipe_options})')

    @property
    def total_eu(self) -> float:
        for material, amount in self.materials.items():
            if material.id == 0:
                return amount
        return 0

    @property
    def eu_per_tick(self) -> float:
        if self.processing_time <= 0:
            return 0
        return self.total_eu / (20 * self.processing_time)

    @property
    def voltage_tier(self) -> int:
        return VoltageTier.voltage_tier_by_eu(abs(self.eu_per_tick))

    @property
    def non_eu_materials(self) -> set[Material]:
        return set(m for m, a in self.materials.items() if a != 0 and not m.is_eu())
