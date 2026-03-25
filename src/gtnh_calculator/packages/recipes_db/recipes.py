from __future__ import annotations
import numpy as np
from typing import Dict
import logging

from .machines import MachineType
from .material import Material
from .machines import Machine
from .raw_recipes import RawRecipe
from .voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


class Recipe:
    id: str
    base_recipe: RawRecipe
    raw_recipe: RawRecipe
    machine: Machine
    category: str
    recipe_special_value: float
    cap: float | None
    cap_specified: bool

    def __init__(
        self,
        id: int,
        base_recipe: RawRecipe,
        raw_recipe: RawRecipe,
        base_machine_type: MachineType,
        machine: Machine,
        cap: float | None,
        cap_specified: bool
    ):
        self.id = id
        self.base_recipe = base_recipe
        self.raw_recipe = raw_recipe
        self.base_machine_type = base_machine_type
        self.machine = machine
        self.cap = cap
        self.cap_specified = cap_specified

    @property
    def materials(self) -> Dict[Material, float]:
        return self.raw_recipe.materials

    @property
    def processing_time(self) -> float:
        return self.raw_recipe.processing_time

    @property
    def minimum_voltage_tier(self) -> int:
        return self.base_recipe.voltage_tier

    @property
    def voltage_tier(self) -> int:
        return self.raw_recipe.voltage_tier

    @property
    def voltage_tier_name(self) -> str:
        return VoltageTier.voltage_tier_name(self.raw_recipe.voltage_tier)

    def __repr__(self) -> str:
        return (f'Recipe {self.id}: {self.raw_recipe}. Machine: {self.machine}, '
                f'Processing Time = {self.processing_time}, Voltage Tier = {self.voltage_tier}')

    def __str__(self) -> str:
        return f'{self.id} | {self.machine}: {self.get_inputs()} -> {self.get_outputs()}'

    def get_inputs(self) -> list[Material]:
        return list(self.raw_recipe.inputs.keys())

    def get_outputs(self) -> list[Material]:
        return list(self.raw_recipe.outputs.keys())

    def material_quantity(self, material: Material):
        return self.materials[material] if material in self.materials.keys() else 0

    def recipe_vector(self, materials: list[Material]):
        return np.array([self.material_quantity(material) for material in materials])

    def input_string_array(self, factor: float) -> list[tuple[float, Material]]:
        result = []
        for material in self.get_inputs():
            if material.is_eu():
                continue
            result.append((factor * (abs(self.material_quantity(material))), material))
        return result

    def input_string(self, factor: float) -> str:
        array = self.input_string_array(factor)
        return ', '.join([f'{"{:.3f}".format(amount)} {material.name}' for amount, material in array])

    def output_string_array(self, factor: float) -> list[tuple[float, Material]]:
        result = []
        for material in self.get_outputs():
            result.append((factor * (abs(self.material_quantity(material))), material))
        return result

    def output_string(self, factor: float) -> str:
        array = self.output_string_array(factor)
        return ', '.join([f'{"{:.3f}".format(amount)} {material.name}' for amount, material in array])

    def non_empty(self) -> bool:
        return (True if self.get_inputs() else False) and (True if self.get_outputs() else False)

    def markdown_inputs(self) -> str:
        return f'''
#### Recipe inputs:

{', \n'.join(f'- {int(abs(a)) if a.is_integer() else abs(a)} {m.name}' 
             for m, a in self.materials.items() if a < 0 and not m.is_eu())}
'''

    def markdown_outputs(self) -> str:
        return f'''
#### Recipe outputs:

{', \n'.join(f'- {int(abs(a)) if a.is_integer() else abs(a)} {m.name}' for m, a in self.materials.items() if a > 0)}
'''
