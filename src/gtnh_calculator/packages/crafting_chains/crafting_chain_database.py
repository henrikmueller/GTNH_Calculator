from __future__ import annotations
import pandas as pd
from typing import Dict
import logging
from dataclasses import dataclass
from itertools import product
from collections import Counter
import math

from ..database_extraction.gtnh_database import GTNHDatabase
from ..database_algorithms.bfs import get_reachable_recipes, get_ingredient_recipes
from ..configs.crafting_chain_config_db import CraftingChainConfig
from ..database_extraction.recipe_initialization import RecipeInitializer
from ..recipes_db.material import Material
from ..recipes_db.machines import Machine
from ..recipes_db.voltage_tiers import VoltageTier
from ..recipes_db.recipes import Recipe
from .crafting_chain_utility import calculate_gradings
from ..utility.general_utility import Timer

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class CraftingChainDatabase:
    database: GTNHDatabase
    config: CraftingChainConfig
    recipes: Dict[str, Recipe]
    recipe_grading: Dict[Recipe, int]
    material_grading: Dict[Material, int]

    @classmethod
    def create_crafting_chain_database(
        cls, database: GTNHDatabase, config: CraftingChainConfig, validity_check: bool = False
    ) -> CraftingChainDatabase:
        with Timer('create_crafting_chain_database', active=True):
            _LOGGER.info(f'Disabled machines: {set(m.name for m in database.extracted_machines.values() if m.disabled)}')
            df = database.filter_recipes(
                database.df_recipes,
                excluded_outputs=set(database.extracted_materials[id] for id in config.disabled_materials),
                voltage_tiers={v for v in VoltageTier.valid_voltage_tiers() if v <= config.max_voltage_tier},
                machines={m for m in database.extracted_machines.values() if not m.disabled}
            )
            df = df[df['MACHINES'].map(len) > 0].drop(columns='TOTAL_EU').copy().reset_index()
            df = df[df['ID'].map(lambda id: id not in config.disabled_recipes)].reset_index()

            starting_materials = config.inputs | config.infinite_materials
            _LOGGER.info(f'Starting materials: {starting_materials}')
            initial_material_grading, df = get_reachable_recipes(
                df, database.extracted_materials, starting_materials, sort=False
            )
            reachable_materials = {m.id: m for m, g in initial_material_grading.items() if g >= 0}
            _LOGGER.info(f'Reachable recipes: {df.shape[0]}')

            target_materials = list(config.outputs.union(config.inputs))
            _, df = get_ingredient_recipes(df, database.extracted_materials, target_materials, sort=False)

            if df.shape[0] <= 0:
                raise ValueError(f'No recipes found for the specified config.')

            # Take the cross product of all input groups
            df = database.blow_up_input_groups(df)

            # Add missing materials from inputs to reachable materials
            for row in df.itertuples(index=False):
                for material in row.TOTAL_INPUTS.keys():
                        reachable_materials[material.id] = material


            def get_machine(row):
                return database.get_default_machine(row, config.default_voltage_tier)

            df['SELECTED_MACHINE'] = df.apply(get_machine, axis=1)
            if not df['SELECTED_MACHINE'].notna().all():
                _LOGGER.warning(
                    'Could not determine the default machine for some recipes. Please check the logs for details.')

            # TODO: Remove materials not part in any recipe

            cc_database = GTNHDatabase(
                df_recipes=df,
                extracted_materials=reachable_materials,
                extracted_machines={k: m for k, m in database.extracted_machines.items()},
                machine_options_book=database.machine_options_book
            )
    
            recipe_initializer = RecipeInitializer(machine_options_book=database.machine_options_book)
            recipes = recipe_initializer.initialize_all(cc_database, config)

            recipe_grading, material_grading = calculate_gradings(
                recipes=list(recipes.values()),
                materials=list(reachable_materials.values()),
                starting_materials=starting_materials
            )

            crafting_chain_database = CraftingChainDatabase(
                database=cc_database,
                config=config,
                recipes=recipes,
                recipe_grading=recipe_grading,
                material_grading=material_grading
            )

            if validity_check:
                crafting_chain_database._validate_recipe_grading()
            return crafting_chain_database

    @property
    def df_recipes(self) -> pd.DataFrame:
        return self.database.df_recipes

    @property
    def extracted_materials(self) -> Dict[str, Material]:
        return self.database.extracted_materials

    @property
    def extracted_machines(self) -> Dict[str, Machine]:
        return self.database.extracted_machines

    def get_recipe_grading_counts(self) -> Counter:
        return Counter(self.recipe_grading.values())

    def get_material_grading_counts(self) -> Counter:
        return Counter(self.material_grading.values())

    def _validate_recipe_grading(self):
        erroneous_gradings = set()
        for recipe in self.recipes.values():
            if self.recipe_grading[recipe] >= 0:
                for material in recipe.consumed_inputs:
                    if self.material_grading[material] > self.recipe_grading[recipe]:
                        erroneous_gradings.add(recipe)
                for material in recipe.get_outputs():
                    if self.material_grading[material] > self.recipe_grading[recipe] + 1:
                        erroneous_gradings.add(recipe)
                if not any(self.material_grading[m] == self.recipe_grading[recipe] for m in recipe.consumed_inputs):
                    erroneous_gradings.add(recipe)
            else:
                if all(self.material_grading[m] >= 0 for m in recipe.consumed_inputs):
                    erroneous_gradings.add(recipe)

        for recipe in erroneous_gradings:
            input_gradings = {m: self.material_grading[m] for m in recipe.get_inputs()}
            output_gradings = {m: self.material_grading[m] for m in recipe.get_outputs()}
            _LOGGER.warning(f'Erroneous grading for recipe {recipe.id} with grading {self.recipe_grading[recipe]}. '
                            f'Material gradings: {input_gradings} (inputs) {output_gradings} (outputs)')
