from frozendict import frozendict
import pandas as pd
import logging
from typing import Dict
from dataclasses import dataclass
from math import isnan

from ..recipes_db.adapted_recipes import AdaptedRecipe
from ..recipes_db.recipes import Recipe
from ..recipes_db.instantiated_recipes import InstantiatedRecipe, RecipeEnvironment
from ..recipes_db.recipe_options import RecipeOptions
from ..recipes_db.machine_options.machine_options import MachineOptions
from ..recipes_db.machine_options.machine_option_books import MachineOptionsBook
from ..recipes_db.machines import Machine
from ..recipes_db.voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


@dataclass
class RecipeInitializer:
    machine_options_book: MachineOptionsBook

    def create_default_machine_options(self, machine: Machine, recipe_options: RecipeOptions) -> MachineOptions:
        selected_options = {}
        for option_type in machine.valid_options:
            options = self.machine_options_book.get_machine_option_list(
                option_type=option_type
            )
            if not isnan(recipe_options.coil_heat):
                options = [o for o in options if o.temperature >= recipe_options.coil_heat]
            if options:
                selected_options[option_type] = min(options, key=lambda o: o.tier)
            else:
                selected_options[option_type] = self.machine_options_book.get_max_machine_option(
                    option_type, lambda o: o.tier)  
        return MachineOptions(
            machine.valid_options,
            selected_options,
            min_tier={t: -1 for t in machine.valid_options}
        )

    def adapt_recipe(self, recipe: Recipe, machine: Machine, machine_options: MachineOptions, voltage_tier: int) -> AdaptedRecipe:
        adapted_recipe = None
        try:
            for v in range(voltage_tier, VoltageTier.MAX + 1):
                try:
                    adapted_recipe = machine.machine_behaviour.fit_recipe(
                        raw_recipe=recipe.raw_recipe,
                        voltage_tier=v,
                        machine_stats=machine.machine_stats,
                        machine_options=machine_options,
                        log=False
                    )
                except ValueError as e:
                    raise ValueError(f'Error occurred while fitting recipe {recipe.raw_recipe} to machine {machine}. VT: {voltage_tier}: {e}')
                if adapted_recipe is None or adapted_recipe.used_parallels > 0 or voltage_tier == VoltageTier.NO_REQUIREMENT:
                    break
                
                # Only continue if raising the voltage tier would allow for parallels
                max_parallels = machine.machine_behaviour.parallel_behaviour.get_parallels(
                    voltage_tier=voltage_tier,
                    machine_options=machine_options
                )
                if max_parallels != 0 or machine.machine_behaviour.parallel_behaviour.parallels_per_voltage_tier == 0:
                    break
        except TypeError as e:
            raise TypeError(f'TypeError occurred while fitting recipe {recipe.raw_recipe} to machine {machine}. VT: {voltage_tier}, {type(voltage_tier)}: {e}')

        if adapted_recipe is None:
            raise ValueError(f'Could not fit recipe {recipe.raw_recipe} to machine {machine} with voltage tier {voltage_tier}')
        return adapted_recipe
    
    def instantiate_recipes(self, df_recipes: pd.DataFrame, pick_any: bool = False) -> Dict[str, InstantiatedRecipe]:
        instantiated_recipes: Dict[str, InstantiatedRecipe] = {}
        for row in df_recipes.itertuples(index=False):
            if row.SELECTED_MACHINE is None:
                continue
            recipe: Recipe = row.RECIPE
            machine: Machine = row.SELECTED_MACHINE
            voltage_tier: int = row.SELECTED_VOLTAGE_TIER
            machine_options = self.create_default_machine_options(machine, recipe.raw_recipe.recipe_options)
            adapted_recipe = self.adapt_recipe(recipe, machine, machine_options, voltage_tier)

            # Take the cross product of all input groups
            for instance_number, input_combination in enumerate(recipe.input_combinations(pick_any=pick_any)):
                recipe_environment = RecipeEnvironment(
                    machine=machine,
                    voltage_tier=voltage_tier,
                    machine_options=machine_options
                )
                instantiated_recipes[recipe.id + str(instance_number)] = InstantiatedRecipe(
                    instance_number=instance_number,
                    base_recipe=recipe,
                    adapted_recipe=adapted_recipe,
                    recipe_environment=recipe_environment,
                    input_combination=input_combination,
                    cap=None,
                    cap_specified=False
                )
        return instantiated_recipes
