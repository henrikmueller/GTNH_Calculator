from __future__ import annotations
import numpy as np
from typing import Dict
import logging

from .material import Material
from .machine import Machine
from .raw_recipes import RawRecipe

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class Recipe:
    id: int
    raw_recipe: RawRecipe
    machine: Machine
    weight: float
    cap: float | None

    def __init__(
        self,
        id: int,
        raw_recipe: RawRecipe,
        machine: Machine,
        weight: float,
        cap: float | None
    ):
        self.id = id
        self.raw_recipe = raw_recipe
        self.machine = machine
        self.weight = weight
        self.cap = cap

    @property
    def materials(self) -> Dict[Material, float]:
        return self.raw_recipe.materials

    @property
    def processing_time(self) -> float:
        return self.raw_recipe.processing_time

    @property
    def voltage_tier(self) -> int:
        return self.machine.voltage_tier

    @property
    def voltage_tier_name(self) -> str:
        return self.machine.voltage_tier_name

    def __repr__(self) -> str:
        return (f'Recipe {self.id}: {self.materials}. Machine: {self.machine}, '
                f'Processing Time = {self.processing_time}, Voltage Tier = {self.voltage_tier}')

    def get_inputs(self) -> list[Material]:
        return [material for material in self.materials.keys() if self.materials[material] < 0]

    def get_outputs(self) -> list[Material]:
        return [material for material in self.materials.keys() if self.materials[material] > 0]

    def get_edge_data(self, eu=False) -> tuple[list[int], list[int]]:
        if eu:
            return [material.id for material in self.get_inputs()], [material.id for material in self.get_outputs()]
        return ([material.id for material in self.get_inputs() if material.id > 0],
                [material.id for material in self.get_outputs()])

    def material_quantity(self, material: Material):
        return self.materials[material] if material in self.materials.keys() else 0

    def recipe_vector(self, materials: list[Material]):
        return np.array([self.material_quantity(material) for material in materials])

    def input_string(self, factor: float):
        result = []
        for material in self.get_inputs():
            if material.name == 'EU':
                continue
            result.append(f'{"{:.2f}".format(factor * (abs(self.material_quantity(material))))} {material.name}')
        return ', '.join(result)

    def output_string(self, factor: float):
        result = []
        for material in self.get_outputs():
            result.append(f'{"{:.2f}".format(factor * (abs(self.material_quantity(material))))} {material.name}')
        return ', '.join(result)

    def non_empty(self) -> bool:
        return (True if self.get_inputs() else False) and (True if self.get_outputs() else False)
