from __future__ import annotations
from frozendict import frozendict
import logging
from dataclasses import dataclass
from itertools import product
from math import prod

from .material import Material, MaterialGroup
from .machines import Machine
from ..recipes_db.recipe_options import RecipeOptions
from .raw_recipes import RawRecipe, InputCombination

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


def get_id(recipe_id: str, instance_number: int) -> str:
    return recipe_id + str(instance_number)


@dataclass(frozen=True)
class Recipe:
    """
    Holds all static information about a recipe, i.e. all information that is not 
    dependent on the machine it is executed in.
    """
    id: str
    raw_recipe: RawRecipe
    valid_machines: frozenset[Machine]

    def input_combinations(
        self, pick_any: bool = False
    ) -> list[InputCombination]:
        material_lists = [g.materials for g in self.raw_recipe.inputs]
        combinations = []
        for instance_number, materials in enumerate(product(*material_lists)):
            input_combination = InputCombination(
                mapping=frozendict(zip(self.raw_recipe.inputs, materials)), instance_number=instance_number)
            if pick_any:
                return [input_combination]
            combinations.append(input_combination)
        return combinations

    def filtered_input_combinations(
        self, selected_inputs: set[Material], selected_instantiated_id: str, 
        enabled_ids: set[str] | None = None, pick_any: bool = False, any_input: bool = True
    ) -> list[InputCombination]:
        input_combinations = self.input_combinations(pick_any=pick_any)
        filtered_combinations = []
        for input_combination in input_combinations:
            id = get_id(self.id, input_combination.instance_number)
            if selected_instantiated_id != "" and id != selected_instantiated_id:
                continue
            if enabled_ids is not None and id not in enabled_ids:
                continue
            if selected_inputs:
                function = any if any_input else all
                if not function(m in selected_inputs for m in input_combination.materials):
                    continue
            if pick_any:
                return [input_combination]
            filtered_combinations.append(input_combination)
        return filtered_combinations
    
    @property
    def input_combination_amount(self) -> int:
        return prod([len(g) for g in self.inputs.keys()])
    
    @property
    def category(self) -> str:
        return self.raw_recipe.category
    
    @property
    def inputs(self) -> frozendict[MaterialGroup, float]:
        return self.raw_recipe.inputs
    
    @property
    def outputs(self) -> list[Material]:
        return [output_spec[0] for output_spec in self.raw_recipe.output_specifications.values()]
    
    @property
    def all_inputs(self) -> set[Material]:
        inputs = set()
        for input_group in self.raw_recipe.inputs.keys():
            inputs |= set(input_group.materials)
        return inputs
    
    @property
    def eu_per_tick(self) -> float:
        return self.raw_recipe.eu_per_tick
    
    @property
    def processing_time(self) -> float:
        return self.raw_recipe.processing_time

    @property
    def total_eu(self) -> float:
        return self.raw_recipe.total_eu
    
    @property
    def voltage_tier(self) -> int:
        return self.raw_recipe.voltage_tier
    
    @property
    def recipe_options(self) -> RecipeOptions:
        return self.raw_recipe.recipe_options
