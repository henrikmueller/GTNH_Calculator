from __future__ import annotations
from typing import Dict, Iterable
import logging
from collections import defaultdict
from dataclasses import dataclass

from .recipe_options import RecipeOptions
from .recipes import Recipe, InputCombination
from .material import Material
from .machines import Machine
from .machine_options.machine_options import MachineOptions, MachineOption
from .machine_options.machine_option_types import MachineOptionType
from .adapted_recipes import AdaptedRecipe
from .voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


@dataclass
class RecipeEnvironment:
    """
    Holds all information about the environment in which a recipe is executed, i.e. the machine, 
    voltage tier and machine options.
    """
    _machine: Machine
    voltage_tier: int
    machine_options: MachineOptions

    def __init__(
        self,
        machine: Machine,
        voltage_tier: int,
        machine_options: MachineOptions,
    ):
        self._machine = machine
        self.voltage_tier = voltage_tier
        self.machine_options = machine_options

    @property
    def machine(self) -> Machine:
        return self._machine
    
    @machine.setter
    def machine(self, machine: Machine) -> None:
        self._machine = machine


@dataclass
class InstantiatedRecipe:
    """
    Holds all information about a recipe: The static base recipe, the environment of the recipe 
    (machine and machine options), the adapted recipe to this machine and the specific input of each input group.
    """
    instance_number: int
    base_recipe: Recipe
    adapted_recipe: AdaptedRecipe
    recipe_environment: RecipeEnvironment
    input_combination: InputCombination
    cap: float | None
    cap_specified: bool

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def id(self) -> str:
        return self.base_recipe.id + str(self.instance_number)
    
    @property
    def valid_machines(self) -> frozenset[Machine]:
        return self.base_recipe.valid_machines

    @property
    def machine(self) -> Machine:
        return self.recipe_environment.machine

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
            if machine not in self.base_recipe.valid_machines:
                raise ValueError(f'Machine {machine} is not valid for recipe {self}')
        if voltage_tier not in machine.voltage_tiers:
            return False
        
        new_machine_options = self.machine_options if machine_option_dict is None \
            else self.machine_options.copy(machine_option_dict)

        adapted_recipe = machine.machine_behaviour.fit_recipe(
            raw_recipe=self.base_recipe.raw_recipe,
            voltage_tier=voltage_tier,
            machine_stats=machine.machine_stats,
            machine_options=new_machine_options,
            log=log
        )
        if adapted_recipe is None:
            _LOGGER.error(f'Could not fit recipe {self} to machine {machine} with voltage tier {voltage_tier}')
            return False
        self.adapted_recipe = adapted_recipe
        self.recipe_environment.machine = machine
        self.recipe_environment.voltage_tier = voltage_tier
        self.recipe_environment.machine_options = new_machine_options
        return True

    @property
    def total_eu(self) -> float:
        return self.adapted_recipe.total_eu  # with parallels

    @property
    def eu_per_tick(self) -> float:
        return self.adapted_recipe.eu_per_tick  # with parallels

    @property
    def processing_time(self) -> float:
        return self.adapted_recipe.processing_time

    @property
    def valid_voltage_tiers(self) -> list[int]:
        if self.base_recipe.raw_recipe.voltage_tier == VoltageTier.NO_REQUIREMENT:
            return [VoltageTier.NO_REQUIREMENT]
        return [v for v in self.machine.voltage_tiers if v >= self.minimum_voltage_tier]

    @property
    def minimum_voltage_tier(self) -> int:
        return self.base_recipe.raw_recipe.voltage_tier

    @property
    def voltage_tier(self) -> int:
        return self.recipe_environment.voltage_tier

    @property
    def voltage_tier_name(self) -> str:
        return VoltageTier.voltage_tier_name(self.voltage_tier)

    def set_voltage_tier(self, voltage_tier: int) -> bool:
        if voltage_tier in self.valid_voltage_tiers:
            self.adapted_recipe = AdaptedRecipe(
                eu_per_tick=self.adapted_recipe.eu_per_tick,
                processing_time=self.adapted_recipe.processing_time,
                amperage=self.adapted_recipe.amperage,
                inputs=self.adapted_recipe.inputs,
                output_specifications=self.adapted_recipe.output_specifications,
                used_parallels=self.adapted_recipe.used_parallels
            )
            return True
        else:
            _LOGGER.warning(f'Cannot set voltage tier {voltage_tier} for machine {self}')
            return False

    @property
    def used_parallels(self) -> int:
        return self.adapted_recipe.used_parallels

    def positive_processing_time(self) -> bool:
        return self.processing_time > 0

    def __repr__(self) -> str:
        return (f'Recipe {self.id}: {self.adapted_recipe}. Machine: {self.machine}, '
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
        return {self.input_combination[g]: a for g, a in self.adapted_recipe.inputs.items()}

    @property
    def output_dict(self) -> Dict[Material, float]:
        # TODO: Take number of output slots into account (e.g. for plant mass)
        result = defaultdict(float)
        for m, a, p in self.adapted_recipe.output_specifications.values():
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
    
    def has_input(self, materials: Iterable[Material], any: bool = True) -> bool:
        if any:
            for material in materials:
                if material in self.input_dict.keys():
                    return True
            return False
        return all(m in self.input_dict.keys() for m in materials)
    
    def has_output(self, materials: Iterable[Material], any: bool = True) -> bool:
        if any:
            for material in materials:
                if material in self.output_dict.keys():
                    return True
            return False
        return all(m in self.output_dict.keys() for m in materials)

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
    
    @property
    def recipe_options(self) -> RecipeOptions:
        return self.base_recipe.raw_recipe.recipe_options
    
    @property
    def machine_options(self) -> MachineOptions:
        return self.recipe_environment.machine_options

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
