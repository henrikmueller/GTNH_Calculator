from __future__ import annotations
import pandas as pd
from typing import Dict, Iterable
import logging
from dataclasses import dataclass

from ..database_extraction.gtnh_database import GTNHDatabase
from ..database_algorithms.bfs import get_reachable_recipes, get_ingredient_recipes
from ..configs.crafting_chain_config_db import CraftingChainConfig
from ..database_extraction.recipe_initialization import RecipeInitializer
from ..recipes_db.material import Material
from ..recipes_db.machines import Machine
from ..recipes_db.recipes import Recipe
from ..recipes_db.voltage_tiers import VoltageTier
from ..recipes_db.instantiated_recipes import InstantiatedRecipe
from .crafting_chain_utility import calculate_gradings
from ..utility.general_utility import Timer
from ..recipes_db.recipe_environments import RecipeEnvironment
from ..streamlit.session_state import StoredRecipeEnvironment

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def filter_recipes(
    df_recipes: pd.DataFrame,
    selected_id: str,
    inputs: Iterable[Material],
    outputs: Iterable[Material],
    voltage_tiers: set[int] | frozenset[int],
    machines: set[Machine] | frozenset[Machine],
    categories: Iterable[str] | None = None,
) -> pd.DataFrame:
    df_result = df_recipes.copy(deep=False)

    if selected_id:
        df_result = df_result[df_result['ID'] == selected_id]
    if inputs:
        df_result = df_result[df_result['RECIPE'].map(lambda r: all(
            any(input in input_group.materials for input_group in r.inputs) for input in inputs)  # type: ignore
        )]
    if outputs:
        df_result = df_result[df_result['RECIPE'].map(lambda r: all(
            output in r.outputs for output in outputs  # type: ignore
        ))]
    if voltage_tiers:
        min_vt, max_vt = min(voltage_tiers), max(voltage_tiers)
        if voltage_tiers and max_vt - min_vt + 1 == len(voltage_tiers):
            df_result = df_result[df_result['RECIPE'].map(lambda r: 
                r.voltage_tier >= min_vt and r.voltage_tier <= max_vt)]  # type: ignore
        else:
            df_result = df_result[df_result['RECIPE'].map(lambda r: 
                r.voltage_tier in voltage_tiers)]  # type: ignore
    if categories:
        df_result = df_result[df_result['RECIPE'].map(lambda r: 
            r.category in categories)]  # type: ignore
    if machines:
        df_result = df_result[df_result['RECIPE'].map(lambda r: bool(r.valid_machines & machines))]  # type: ignore
    return df_result


@dataclass
class CraftingChainDatabase:
    config: CraftingChainConfig
    recipe_ids: frozenset[str]
    material_ids: frozenset[str]
    machine_ids: frozenset[str]
    recipe_specifications: Dict[str, InstantiatedRecipe]
    recipe_initializer: RecipeInitializer

    @classmethod
    def create_crafting_chain_database(
        cls, database: GTNHDatabase, config: CraftingChainConfig
    ) -> CraftingChainDatabase:
        with Timer('reduce_recipes', active=True):
            _LOGGER.info(f'Disabled machines: {set(m.name for m in database.extracted_machines.values() if m.disabled or m in config.disabled_machines)}')
            allowed_machines = {
                m for m in database.extracted_machines.values() if not m.disabled and m not in config.disabled_machines
                and m.unlock_tier <= config.unlocked_voltage_tier
            }
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
                for material in row.RECIPE.all_inputs:  # type: ignore
                    reachable_materials[material.id] = material

            recipe_ids = frozenset(df['ID'])
            material_ids = frozenset(reachable_materials.keys())
            machine_ids = frozenset(m.id for m in allowed_machines)

        recipe_initializer = RecipeInitializer(database.machine_options_book)
        crafting_chain_database = CraftingChainDatabase(
            config=config,
            recipe_ids=recipe_ids,
            material_ids=material_ids,
            machine_ids=machine_ids,
            recipe_specifications={},
            recipe_initializer=recipe_initializer
        )
        return crafting_chain_database

    def df_recipes(self, database: GTNHDatabase) -> pd.DataFrame:
        return database.df_recipes[database.df_recipes['ID'].isin(self.recipe_ids)]

    def materials(self, database: GTNHDatabase) -> Dict[str, Material]:
        return {id: database.extracted_materials[id] for id in self.material_ids}

    def machines(self, database: GTNHDatabase) -> Dict[str, Machine]:
        return {id: database.extracted_machines[id] for id in self.machine_ids}
    
    def instantiate(
        self, recipe: Recipe, pick_any: bool = False, changed_recipe_environments: Dict[str, tuple[RecipeEnvironment, StoredRecipeEnvironment]] = {}
    ) -> list[InstantiatedRecipe]:
        return self.recipe_initializer.instantiate(
            recipe=recipe, config=self.config, pick_any=pick_any, 
            changed_recipe_environments=changed_recipe_environments
        )
    
    def instantiate_all(
        self, df_recipes: pd.DataFrame, pick_any: bool = False, 
        changed_recipe_environments: Dict[str, tuple[RecipeEnvironment, StoredRecipeEnvironment]] = {}
    ) -> Dict[str, InstantiatedRecipe]:
        return self.recipe_initializer.instantiate_all(
            df_recipes=df_recipes, config=self.config, pick_any=pick_any, 
            changed_recipe_environments=changed_recipe_environments
        )
    
    def number_of_instantiated_recipes(self, df_recipes: pd.DataFrame) -> int:
        if df_recipes.empty:
            return 0
        return sum(recipe.input_combination_amount for recipe in df_recipes["RECIPE"])
    
    def calculate_gradings(self, instantiated_recipe_list: list[InstantiatedRecipe], materials: Dict[str, Material], 
        starting_materials: set[Material]
    ) -> tuple[Dict[str, int], Dict[Material, int]]:
        return calculate_gradings(
            instantiated_recipe_list=instantiated_recipe_list,
            materials=materials,
            starting_materials=starting_materials
        )

    # def _validate_recipe_grading(self):
    #     erroneous_gradings = set()
    #     for recipe in self.instantiated_recipes.values():
    #         if self.recipe_grading[recipe] >= 0:
    #             for material in recipe.consumed_inputs:
    #                 if self.material_grading[material] > self.recipe_grading[recipe]:
    #                     erroneous_gradings.add(recipe)
    #             for material in recipe.get_outputs():
    #                 if self.material_grading[material] > self.recipe_grading[recipe] + 1:
    #                     erroneous_gradings.add(recipe)
    #             if not any(self.material_grading[m] == self.recipe_grading[recipe] for m in recipe.consumed_inputs):
    #                 erroneous_gradings.add(recipe)
    #         else:
    #             if all(self.material_grading[m] >= 0 for m in recipe.consumed_inputs):
    #                 erroneous_gradings.add(recipe)

    #     for recipe in erroneous_gradings:
    #         input_gradings = {m: self.material_grading[m] for m in recipe.get_inputs()}
    #         output_gradings = {m: self.material_grading[m] for m in recipe.get_outputs()}
    #         _LOGGER.warning(f'Erroneous grading for recipe {recipe.id} with grading {self.recipe_grading[recipe]}. '
    #                         f'Material gradings: {input_gradings} (inputs) {output_gradings} (outputs)')
