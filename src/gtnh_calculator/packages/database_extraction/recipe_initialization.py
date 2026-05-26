import pandas as pd
import logging
from typing import Dict
from dataclasses import dataclass
from math import isnan

from ..recipes_db.recipes import Recipe
from ..recipes_db.raw_recipes import RawRecipe
from ..recipes_db.recipe_options import RecipeOptions
from ..recipes_db.machine_options.machine_options import MachineOptions
from ..recipes_db.machine_options.machine_option_books import MachineOptionsBook
from ..recipes_db.machines import Machine
from ..recipes_db.voltage_tiers import VoltageTier
from ..database_extraction.gtnh_database import GTNHDatabase
from ..configs.crafting_chain_config_db import CraftingChainConfig

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

    def create_recipe_from_row(self, recipe_row, default_voltage_tier: int | None = None) -> Recipe:
        base_recipe = RawRecipe(
            eu_per_tick=-recipe_row.VOLTAGE * recipe_row.AMPERAGE,
            processing_time=recipe_row.DURATION,
            amperage=recipe_row.AMPERAGE,
            voltage_tier=recipe_row.VOLTAGE_TIER,
            inputs=recipe_row.TOTAL_INPUTS,
            output_specifications=recipe_row.OUTPUTS,
            recipe_options=recipe_row.RECIPE_OPTIONS
        )
        machine: Machine = recipe_row.SELECTED_MACHINE

        if default_voltage_tier is None:
            valid_voltage_tiers = [v for v in machine.voltage_tiers if base_recipe.voltage_tier <= v]
        else:
            valid_voltage_tiers = [v for v in machine.voltage_tiers if base_recipe.voltage_tier <= v <= default_voltage_tier]

        if valid_voltage_tiers:
            voltage_tier = min(valid_voltage_tiers) if default_voltage_tier is None else max(valid_voltage_tiers)
        else:
            _LOGGER.debug(f'No valid voltage tier found for machine {machine} and recipe {recipe_row.ID}. '
                        f'Recipe voltage tier: {base_recipe.voltage_tier}, '
                        f'default voltage tier: {default_voltage_tier}')
            voltage_tier = base_recipe.voltage_tier
        
        machine_options = self.create_default_machine_options(machine, base_recipe.recipe_options)

        raw_recipe = None
        for v in range(voltage_tier, VoltageTier.MAX + 1):
            raw_recipe = machine.machine_behaviour.fit_recipe(
                raw_recipe=base_recipe,
                voltage_tier=v,
                machine_stats=machine.machine_stats,
                machine_options=machine_options,
                log=False
            )
            if raw_recipe is None or raw_recipe.used_parallels > 0:
                break
            
            max_parallels = machine.machine_behaviour.parallel_behaviour.get_parallels(
                voltage_tier=voltage_tier,
                machine_options=machine_options
            )
            if max_parallels != 0 or machine.machine_behaviour.parallel_behaviour.parallels_per_voltage_tier == 0:
                break

        if raw_recipe is None:
            raise ValueError(f'Could not fit recipe {recipe_row} to machine {machine} with voltage tier {voltage_tier}')
        return Recipe(
            id=recipe_row.ID,
            base_recipe=base_recipe,
            raw_recipe=raw_recipe,
            valid_machines=recipe_row.MACHINES,
            machine=machine,
            machine_options=machine_options,
            cap=None,
            cap_specified=False
        )
    
    def initialize_all(self, database: GTNHDatabase, config: CraftingChainConfig) -> Dict[str, Recipe]:
        recipes = {}
        for row in database.df_recipes.itertuples(index=False):
            if row.SELECTED_MACHINE is None:
                continue
            recipes[row.ID] = self.create_recipe_from_row(row, config.default_voltage_tier)
        return recipes
