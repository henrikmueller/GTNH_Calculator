from __future__ import annotations
import pandas as pd
from typing import Dict, Iterable
import logging
from dataclasses import dataclass
from collections import Counter
from math import isnan

from ..database_extraction.gtnh_database import GTNHDatabase
from ..database_algorithms.bfs import get_reachable_recipes, get_ingredient_recipes
from ..configs.crafting_chain_config_db import CraftingChainConfig
from ..database_extraction.recipe_initialization import RecipeInitializer
from ..recipes_db.material import Material
from ..recipes_db.machines import Machine
from ..recipes_db.voltage_tiers import VoltageTier
from ..recipes_db.instantiated_recipes import InstantiatedRecipe
from .crafting_chain_utility import calculate_gradings
from ..utility.general_utility import Timer, print_df

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class CraftingChainDatabase:
    database: GTNHDatabase
    config: CraftingChainConfig
    instantiated_recipes: Dict[str, InstantiatedRecipe]
    recipe_grading: Dict[InstantiatedRecipe, int]
    material_grading: Dict[Material, int]

    @classmethod
    def create_crafting_chain_database(
        cls, database: GTNHDatabase, config: CraftingChainConfig, validity_check: bool = False
    ) -> CraftingChainDatabase:
        with Timer('create_crafting_chain_database', active=True):
            _LOGGER.info(f'Disabled machines: {set(m.name for m in database.extracted_machines.values() if m.disabled or m in config.disabled_machines)}')
            allowed_machines = {m for m in database.extracted_machines.values() if not m.disabled and m not in config.disabled_machines}
            df = database.filter_recipes(
                database.df_recipes,
                excluded_ids=config.disabled_recipe_ids,
                excluded_outputs=config.disabled_materials,
                allowed_machines=allowed_machines,
                voltage_tiers={v for v in VoltageTier.valid_voltage_tiers() if v <= config.max_voltage_tier}
            )

            target_materials = list(config.outputs.union(config.inputs))
            _LOGGER.info(f'Outputs: {config.outputs}')
            _LOGGER.info(f'Target materials: {target_materials}')
            _, df = get_ingredient_recipes(df, database.extracted_materials, target_materials, sort=False)

            starting_materials = config.inputs | config.infinite_materials
            _LOGGER.info(f'Starting materials: {starting_materials}')
            initial_material_grading, df = get_reachable_recipes(
                df, database.extracted_materials, starting_materials, sort=False
            )
            reachable_materials = {m.id: m for m, g in initial_material_grading.items() if g >= 0}
            _LOGGER.info(f'Reachable recipes: {df.shape[0]}')

            if df.shape[0] <= 0:
                raise ValueError(f'No recipes found for the specified config.')

            # Add missing materials from inputs to reachable materials
            for row in df.itertuples(index=False):
                for material in row.RECIPE.all_inputs:
                    reachable_materials[material.id] = material

            def get_machine(row):
                return database.get_default_machine_and_voltage_tier(
                    row, config.default_voltage_tier, config.max_voltage_tier, prefer_singleblocks=True)

            df[['SELECTED_MACHINE', 'SELECTED_VOLTAGE_TIER']] = df.apply(
                get_machine,
                axis=1,
                result_type='expand'
            )
            if not df['SELECTED_MACHINE'].notna().all():
                count = df["SELECTED_MACHINE"].isna().sum()
                _LOGGER.warning(
                    f'Could not determine the default machine for {count} recipes. Please check the logs for details.')
                # print_df(df[df['SELECTED_MACHINE'].isna()])

            cc_database = GTNHDatabase(
                df_recipes=df,
                extracted_materials=reachable_materials,
                extracted_machines={k: m for k, m in database.extracted_machines.items()},
                machine_options_book=database.machine_options_book
            )
    
            recipe_initializer = RecipeInitializer(machine_options_book=database.machine_options_book)
            instantiated_recipes = recipe_initializer.instantiate_recipes(cc_database.df_recipes)


            recipe_grading, material_grading = calculate_gradings(
                instantiated_recipes=list(instantiated_recipes.values()),
                materials=reachable_materials.values(),
                starting_materials=starting_materials
            )

            crafting_chain_database = CraftingChainDatabase(
                database=cc_database,
                config=config,
                instantiated_recipes=instantiated_recipes,
                recipe_grading=recipe_grading,
                material_grading=material_grading
            )

            for recipe in crafting_chain_database.instantiated_recipes.values():
                if isnan(recipe.eu_per_tick):
                    _LOGGER.warning(f'NAN in recipe eu/t {recipe}')

            if validity_check:
                crafting_chain_database._validate_recipe_grading()
            return crafting_chain_database

    @property
    def df_recipes(self) -> pd.DataFrame:
        return self.database.df_recipes

    @property
    def materials(self) -> Iterable[Material]:
        return self.material_grading.keys()

    @property
    def extracted_machines(self) -> Dict[str, Machine]:
        return self.database.extracted_machines

    def get_recipe_grading_counts(self) -> Counter:
        return Counter(self.recipe_grading.values())

    def get_material_grading_counts(self) -> Counter:
        return Counter(self.material_grading.values())

    def _validate_recipe_grading(self):
        erroneous_gradings = set()
        for recipe in self.instantiated_recipes.values():
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
