from __future__ import annotations
import numpy as np
from typing import Dict
import logging

from .machine_types import MachineType
from .machine_options.machine_options import MachineOptions
from .material import Material
from .machine import Machine
from .raw_recipes import RawRecipe
from .machine_options.machine_option_books import MachineOptionsBook
from .voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class Recipe:
    id: int
    base_recipe: RawRecipe
    raw_recipe: RawRecipe
    base_machine_type: MachineType
    machine: Machine
    weight: float
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
        return self.machine.voltage_tier

    @property
    def voltage_tier_name(self) -> str:
        return self.machine.voltage_tier_name

    @property
    def weight(self) -> float:
        return self.machine.machine_type.weight

    def __repr__(self) -> str:
        return (f'Recipe {self.id}: {self.materials}. Machine: {self.machine}, '
                f'Processing Time = {self.processing_time}, Voltage Tier = {self.voltage_tier}')

    def __str__(self) -> str:
        return f'{self.id} | {self.machine}: {self.get_inputs()} -> {self.get_outputs()}'

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

    def fit_to_machine(self) -> None:
        self.raw_recipe = self.machine.fit_recipe(self.base_recipe)

    def update(
        self,
        config=None,
        machine_options_book: MachineOptionsBook | None = None,
        machine_type: MachineType | None = None,
        machine_options: MachineOptions | None = None,
        voltage_tier: int | None = None,
    ) -> None:
        if machine_type is not None:
            if config is None:
                raise ValueError(f'Specify config to update the machine type')
            self.machine.machine_type = machine_type
            if not self.cap_specified:
                self.cap = config.max_multiblock_machines if machine_type.multiblock else (
                    config.max_singleblock_machines)
            if machine_options is None:
                if machine_options_book is None:
                    raise ValueError(f'Specify machine options book to update the machine type')
                default_options = machine_options_book.get_default_options(
                    self.raw_recipe, machine_type, config.default_machine_options
                )
                self.machine.machine_options = default_options
        if machine_options is not None:
            self.machine.machine_options = machine_options
        if voltage_tier is not None:
            self.machine.voltage_tier = voltage_tier
        self.fit_to_machine()

    def energy_per_base_recipe(self) -> float:
        return self.raw_recipe.total_eu / self.base_recipe_count()

    def base_recipe_count(self) -> float:
        materials = self.raw_recipe.non_eu_materials
        if materials == self.base_recipe.non_eu_materials:
            ratios = set(self.raw_recipe.materials[m] / self.base_recipe.materials[m] for m in materials)
            if not ratios:
                raise AssertionError(f'No non EU Materials in recipe {self}')
            if len(ratios) == 1:
                return list(ratios)[0]
            if min(ratios) / max(ratios) >= 0.9999:
                # In this case get the closest ratio to an integer
                int_distances = [(r, abs(r - round(r))) for r in ratios]
                return min(int_distances, key=lambda x: x[1])[0]
            raise AssertionError(f'Raw recipe and base recipe are not linearly dependent:'
                                 f'Raw: {self.raw_recipe}. Base: {self.base_recipe}. Ratios: {ratios}'
                                 f'More accurately: {[(m, self.raw_recipe.materials[m] / self.base_recipe.materials[m]) for m in materials]}')
        raise AssertionError(f'Raw recipe and base recipe use different materials. '
                             f'Raw: {self.raw_recipe}. Base: {self.base_recipe}')

    def select_suitable_voltage_tier(
        self,
        max_voltage_tier: int,
        machine_amount: float,
        max_machine_amount: float,
        maximal_energy_increase: float | None
    ) -> None:
        current_voltage_tier = self.voltage_tier
        if current_voltage_tier == VoltageTier.NO_REQUIREMENT:
            return
        current_energy_per_base_recipe = self.energy_per_base_recipe()
        current_throughput = machine_amount * self.base_recipe_count() / self.processing_time
        _LOGGER.debug(f'Tier: {self.voltage_tier}, Amount: {machine_amount}')
        for voltage_tier in range(self.voltage_tier + 1, max_voltage_tier + 1):
            self.update(voltage_tier=voltage_tier)
            if current_energy_per_base_recipe == 0:
                _LOGGER.error(self)
            energy_percentage = self.energy_per_base_recipe() / current_energy_per_base_recipe
            _LOGGER.debug(f'Tier: {voltage_tier}, energy_percentage: {energy_percentage}')
            if maximal_energy_increase is not None and energy_percentage > maximal_energy_increase:
                self.update(voltage_tier=current_voltage_tier)
                return
            current_voltage_tier = voltage_tier
            new_machine_amount = current_throughput * self.processing_time / self.base_recipe_count()
            _LOGGER.debug(f'Tier: {voltage_tier}, Amount: {new_machine_amount}')
            if new_machine_amount <= max_machine_amount:
                return

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
