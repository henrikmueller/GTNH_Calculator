from __future__ import annotations
from typing import Dict, Iterable
import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from frozendict import frozendict

from .recipe_options import RecipeOptions
from .recipes import Recipe, InputCombination, get_id
from .raw_recipes import RawRecipe
from .material import Material
from .machines import Machine
from .machine_options.machine_options import MachineOptions, MachineOption
from .machine_options.machine_option_types import MachineOptionType
from .adapted_recipes import AdaptedRecipe, InvalidAdaptedRecipe, ThroughputRatio, PartiallyUtilizedRecipe
from .recipe_environments import RecipeEnvironment
from .behaviours.machine_behaviours import FittingContext
from .voltage_tiers import VoltageTier
from ..utility.general_utility import format_float

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


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
    def base_id(self) -> str:
        return self.base_recipe.id

    @property
    def id(self) -> str:
        return get_id(self.base_id, self.instance_number)

    @property
    def raw_recipe(self) -> RawRecipe:
        return self.base_recipe.raw_recipe
    
    @property
    def valid_machines(self) -> frozenset[Machine]:
        return self.base_recipe.valid_machines

    @property
    def is_valid(self) -> bool:
        return self.adapted_recipe.is_valid

    @property
    def machine(self) -> Machine:
        return self.recipe_environment.machine

    @property
    def total_eu(self) -> float:
        return self.adapted_recipe.total_eu  # with parallels

    @property
    def eu_per_tick(self) -> float:
        return self.adapted_recipe.eu_per_tick  # with parallels

    @property
    def amperage(self) -> int:
        return self.adapted_recipe.amperage

    @property
    def processing_time(self) -> float:
        return self.adapted_recipe.processing_time

    @property
    def valid_voltage_tiers(self) -> list[int]:
        if self.raw_recipe.voltage_tier == VoltageTier.NO_REQUIREMENT:
            return [VoltageTier.NO_REQUIREMENT]
        return [v for v in self.machine.voltage_tiers if v >= self.minimum_voltage_tier]

    @property
    def minimum_voltage_tier(self) -> int:
        return self.raw_recipe.voltage_tier

    @property
    def voltage_tier(self) -> int:
        return self.recipe_environment.voltage_tier

    @property
    def voltage_tier_name(self) -> str:
        return VoltageTier.voltage_tier_name(self.voltage_tier)

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
    def positive_outputs(self) -> list[Material]:
        return [m for m, a in self.output_dict.items() if a > 0]

    @property
    def input_dict(self) -> frozendict[Material, float]:
        return self.adapted_recipe.input_dict(self.input_combination)

    @property
    def output_dict(self) -> frozendict[Material, float]:
        return frozendict(self.adapted_recipe.output_dict)

    @property
    def output_specifications(self) -> frozendict[int, tuple[Material, float, float]]:
        return frozendict(self.adapted_recipe.output_specifications)

    @property
    def parallelized(self) -> bool:
        return self.used_parallels > 1

    @property
    def material_dict(self) -> frozendict[Material, float]:
        result = defaultdict(float)
        for input, amount in self.input_dict.items():
            result[input] += amount
        for output, amount in self.output_dict.items():
            result[output] += amount
        return frozendict(result)
    
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

    def non_empty(self) -> bool:
        return (True if self.get_inputs() else False) and (True if self.get_outputs() else False)
    
    @property
    def recipe_options(self) -> RecipeOptions:
        return self.raw_recipe.recipe_options
    
    @property
    def machine_options(self) -> MachineOptions:
        return self.recipe_environment.machine_options

    def get_throughput_ratio(self, instantiated_recipe: InstantiatedRecipe) -> ThroughputRatio:
        if not instantiated_recipe.adapted_recipe.is_valid:
            return ThroughputRatio(0.0)
        if self.raw_recipe == instantiated_recipe.raw_recipe:
            return self.adapted_recipe.get_throughput_ratio(instantiated_recipe.adapted_recipe, self.raw_recipe)
        raise ValueError(f"Cannot compute throughput ratio of recipes with different raw recipes: {self.raw_recipe} and {instantiated_recipe.raw_recipe}")

    def fit_to_capacity_utilization(self, capacity_utilization: float, log: bool = False) -> InstantiatedPartialRecipe:
        partially_utilized_recipe = self.machine.capacity_utilization_behaviour.fit_to_capacity_utilization(
            adapted_recipe=self.adapted_recipe,
            capacity_utilization=capacity_utilization,
            machine_behaviour=self.machine.machine_behaviour,
            fitting_context=FittingContext(
                raw_recipe=self.raw_recipe,
                voltage_tier=self.voltage_tier,
                machine_stats=self.machine.machine_stats,
                machine_options=self.machine_options
            ),
            log=log
        )
        return InstantiatedPartialRecipe(
            instantiated_recipe=self,
            partially_utilized_recipe=partially_utilized_recipe
        )

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

    def average_eu_per_tick_str(self, factor: float = 1.0) -> str:
        return f"{format_float(abs(factor * self.eu_per_tick), decimal_places=1, separate_thousands=True)} EU/t ({self.amperage}A)"

    def average_total_eu_str(self, factor: float = 1.0) -> str:
        return f"{format_float(abs(factor * self.total_eu), decimal_places=1, separate_thousands=True)} EU"

    def used_parallels_str(self) -> str:
        return f"{format_float(self.used_parallels, separate_thousands=True)}"


@dataclass
class InstantiatedPartialRecipe:
    instantiated_recipe: InstantiatedRecipe
    partially_utilized_recipe: PartiallyUtilizedRecipe

    @property
    def id(self) -> str:
        return self.instantiated_recipe.id

    @property
    def base_recipe(self) -> Recipe:
        return self.instantiated_recipe.base_recipe

    @property
    def recipe_environment(self) -> RecipeEnvironment:
        return self.instantiated_recipe.recipe_environment

    @property
    def input_combination(self) -> InputCombination:
        return self.instantiated_recipe.input_combination

    @property
    def capacity_utilization(self) -> float:
        return self.partially_utilized_recipe.capacity_utilization

    @property
    def processing_time(self) -> float:
        return self.partially_utilized_recipe.processing_time

    def positive_processing_time(self) -> bool:
        return self.instantiated_recipe.positive_processing_time()

    @property
    def min_total_eu(self) -> float:
        return self.partially_utilized_recipe.min_total_eu

    @property
    def max_total_eu(self) -> float:
        return self.partially_utilized_recipe.max_total_eu

    @property
    def min_eu_per_tick(self) -> float:
        return self.partially_utilized_recipe.min_eu_per_tick

    @property
    def max_eu_per_tick(self) -> float:
        return self.partially_utilized_recipe.max_eu_per_tick

    @property
    def input_dict(self) -> frozendict[Material, float]:
        return self.partially_utilized_recipe.input_dict(self.input_combination)

    @property
    def consumed_input_dict(self) -> frozendict[Material, float]:
        return frozendict({m: a for m, a in self.input_dict.items() if a < 0})

    @property
    def output_dict(self) -> frozendict[Material, float]:
        return frozendict(self.partially_utilized_recipe.output_dict)

    @property
    def positive_outputs(self) -> list[Material]:
        return [m for m, a in self.output_dict.items() if a > 0]

    @property
    def output_specifications(self) -> frozendict[int, tuple[Material, float, float]]:
        return frozendict(self.partially_utilized_recipe.output_specifications)

    @property
    def used_materials(self) -> set[Material]:
        return set(self.input_dict.keys()) | set(self.output_dict.keys())

    @property
    def is_valid(self) -> bool:
        return self.partially_utilized_recipe.is_valid
    
    @property
    def valid_machines(self) -> frozenset[Machine]:
        return self.base_recipe.valid_machines

    @property
    def machine(self) -> Machine:
        return self.recipe_environment.machine

    @property
    def raw_recipe(self) -> RawRecipe:
        return self.base_recipe.raw_recipe
    
    @property
    def recipe_options(self) -> RecipeOptions:
        return self.raw_recipe.recipe_options

    @property
    def parallelized(self) -> bool:
        return self.partially_utilized_recipe.parallelized

    @property
    def voltage_tier(self) -> int:
        return self.recipe_environment.voltage_tier

    @property
    def voltage_tier_name(self) -> str:
        return VoltageTier.voltage_tier_name(self.voltage_tier)

    def average_eu_per_tick_str(self, factor: float = 1.0) -> str:
        min_eu_str = format_float(abs(factor * self.min_eu_per_tick), decimal_places=1, separate_thousands=True)
        max_eu_str = format_float(abs(factor * self.max_eu_per_tick), decimal_places=1, separate_thousands=True)
        if min_eu_str == max_eu_str:
            return f"{min_eu_str} EU/t"
        return (f"{min_eu_str} – {max_eu_str} EU/t  (depending on parallelization)")

    def average_total_eu_str(self, factor: float = 1.0) -> str:
        min_eu_str = format_float(abs(factor * self.min_total_eu), decimal_places=1, separate_thousands=True)
        max_eu_str = format_float(abs(factor * self.max_total_eu), decimal_places=1, separate_thousands=True)
        if min_eu_str == max_eu_str:
            return f"{min_eu_str} EU"
        return (f"{min_eu_str} – {max_eu_str} EU  (depending on parallelization)")

    def input_string(self, factor: float) -> str:
        return ', '.join([f'{"{:.3f}".format(factor * abs(amount))} {material.name}' for material, amount in self.consumed_input_dict.items()])

    def output_string(self, factor: float) -> str:
        return ', '.join([f'{"{:.3f}".format(factor * abs(amount))} {material.name}' for material, amount in self.output_dict.items()])

    def used_parallels_str(self) -> str:
        return f"Depending on input supply"
