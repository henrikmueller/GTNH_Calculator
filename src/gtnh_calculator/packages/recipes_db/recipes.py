from __future__ import annotations
import numpy as np
from typing import Dict
import logging
from collections import defaultdict

from .material import Material
from .machines import Machine
from .machine_options.machine_options import MachineOptions, MachineOption
from .machine_options.machine_option_types import MachineOptionType
from .raw_recipes import RawRecipe
from .voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


class Recipe:
    id: str
    base_recipe: RawRecipe
    raw_recipe: RawRecipe
    valid_machines: set[Machine]
    _machine: Machine
    machine_options: MachineOptions
    cap: float | None
    cap_specified: bool

    def __init__(
        self,
        id: str,
        base_recipe: RawRecipe,
        raw_recipe: RawRecipe,
        valid_machines: set[Machine],
        machine: Machine,
        machine_options: MachineOptions,
        cap: float | None,
        cap_specified: bool
    ):
        self.id = id
        self.base_recipe = base_recipe
        self.raw_recipe = raw_recipe
        self.valid_machines = valid_machines
        self._machine = machine
        self.machine_options = machine_options
        self.cap = cap
        self.cap_specified = cap_specified

    @property
    def machine(self) -> Machine:
        return self._machine

    @machine.setter
    def machine(self, machine: Machine) -> None:
        self.update(machine=machine)

    def update(
        self, 
        machine: Machine | None = None, 
        voltage_tier: int | None = None, 
        machine_option_dict: Dict[MachineOptionType, MachineOption] | None = None,
        log: bool = False
    ) -> bool:
        """
        Update the recipe.
        """
        voltage_tier = self.voltage_tier if voltage_tier is None else voltage_tier
        if machine is None:
            machine = self.machine
        else:
            if machine not in self.valid_machines:
                raise ValueError(f'Machine {machine} is not valid for recipe {self}')
        if voltage_tier not in machine.voltage_tiers:
            return False
        
        new_machine_options = self.machine_options if machine_option_dict is None \
            else self.machine_options.copy(machine_option_dict)

        new_raw_recipe = machine.machine_behaviour.fit_recipe(
            raw_recipe=self.base_recipe,
            voltage_tier=voltage_tier,
            machine_stats=machine.machine_stats,
            machine_options=new_machine_options,
            log=log
        )
        if new_raw_recipe is None:
            _LOGGER.error(f'Could not fit recipe {self} to machine {machine} with voltage tier {voltage_tier}')
            return False
        self.raw_recipe = new_raw_recipe
        self._machine = machine
        self.machine_options = new_machine_options
        return True

    @property
    def total_eu(self) -> float:
        return self.raw_recipe.total_eu  # with parallels

    @property
    def eu_per_tick(self) -> float:
        return self.raw_recipe.eu_per_tick  # with parallels

    @property
    def processing_time(self) -> float:
        return self.raw_recipe.processing_time

    @property
    def minimum_voltage_tier(self) -> int:
        return self.base_recipe.voltage_tier

    @property
    def valid_voltage_tiers(self) -> list[int]:
        return [v for v in self.machine.voltage_tiers if v >= self.minimum_voltage_tier]

    @property
    def voltage_tier(self) -> int:
        return self.raw_recipe.voltage_tier

    def set_voltage_tier(self, voltage_tier: int) -> bool:
        if voltage_tier in self.valid_voltage_tiers:
            self.raw_recipe.voltage_tier = voltage_tier
            return True
        else:
            _LOGGER.warning(f'Cannot set voltage tier {voltage_tier} for machine {self}')
            return False

    @property
    def used_parallels(self) -> int:
        return self.raw_recipe.used_parallels

    @property
    def voltage_tier_name(self) -> str:
        return VoltageTier.voltage_tier_name(self.raw_recipe.voltage_tier)

    def positive_processing_time(self) -> bool:
        return self.processing_time > 0

    def __repr__(self) -> str:
        return (f'Recipe {self.id}: {self.raw_recipe}. Machine: {self.machine}, '
                f'Processing Time = {self.processing_time}, Voltage Tier = {self.voltage_tier}')

    def __str__(self) -> str:
        return f'{self.id} | {self.machine}: {self.get_inputs()} -> {self.get_outputs()}'

    def get_inputs(self) -> list[Material]:
        return list(self.input_dict.keys())

    @property
    def consumed_inputs(self) -> list[Material]:
        return [m for m, a in self.input_dict.items() if a < 0]

    def get_outputs(self) -> list[Material]:
        return list(self.output_dict.keys())

    @property
    def input_dict(self) -> Dict[Material, float]:
        return self.raw_recipe.inputs

    @property
    def output_dict(self) -> Dict[Material, float]:
        # TODO: Take number of output slots into account (e.g. for plant mass)
        result = defaultdict(float)
        for m, a, p in self.raw_recipe.output_specifications.values():
            result[m] += a * p
        return result

    @property
    def material_dict(self) -> Dict[Material, float]:
        result = defaultdict(float)
        for input, amount in self.input_dict.items():
            result[input] += amount
        for output, amount in self.output_dict.items():
            result[output] += amount
        return result

    @property
    def materials(self) -> list[Material]:
        return list(self.material_dict.keys())

    def material_quantity(self, material: Material):
        return self.material_dict[material] if material in self.material_dict.keys() else 0

    def input_string_array(self, factor: float) -> list[tuple[float, Material]]:
        result = []
        for material in self.consumed_inputs:
            result.append((factor * (abs(self.material_quantity(material))), material))
        return result

    def input_string(self, factor: float) -> str:
        array = self.input_string_array(factor)
        return ', '.join([f'{"{:.3f}".format(amount)} {material.name}' for amount, material in array])

    def output_string_array(self, factor: float) -> list[tuple[float, Material]]:
        result = []
        for material, amount in self.output_dict.items():
            if amount == 0:
                continue
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
             for m, a in self.material_dict.items() if a < 0)}
'''

    def markdown_outputs(self) -> str:
        return f'''
#### Recipe outputs:

{', \n'.join(f'- {int(abs(a)) if a.is_integer() else abs(a)} {m.name}' for m, a in self.material_dict.items() if a > 0)}
'''
