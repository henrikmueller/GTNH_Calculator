from __future__ import annotations
import pandas as pd
from typing import Dict
import logging
from dataclasses import dataclass
from itertools import product
from collections import Counter

from ..database_extraction.database_extractor import GTNHDatabase
from ..configs.crafting_chain_config_db import CraftingChainConfig
from ..recipes_db.machines import Machine
from ..recipes_db.machine_options.machine_options import MachineOptions
from ..recipes_db.machine_options.machine_option_types import MachineOptionType
from ..recipes_db.material import Material
from ..recipes_db.voltage_tiers import VoltageTier
from ..recipes_db.raw_recipes import RawRecipe
from ..recipes_db.recipes import Recipe
from ..recipes_db.recipe_options import RecipeOptions
from .crafting_chain_utility import calculate_gradings
from ..utility.general_utility import Timer

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


def create_recipe_from_row(recipe_row, default_voltage_tier: int) -> Recipe:
    base_recipe = RawRecipe(
        eu_per_tick=-recipe_row.VOLTAGE * recipe_row.AMPERAGE,
        processing_time=recipe_row.DURATION,
        amperage=recipe_row.AMPERAGE,
        voltage_tier=recipe_row.VOLTAGE_TIER,
        inputs=recipe_row.TOTAL_INPUTS,
        output_specifications=recipe_row.OUTPUTS,
        recipe_options=RecipeOptions.get_recipe_options(recipe_row.METADATA, recipe_row.ADDITIONAL_INFO)
    )
    machine = recipe_row.SELECTED_MACHINE
    valid_voltage_tiers = [v for v in machine.voltage_tiers if base_recipe.voltage_tier <= v <= default_voltage_tier]
    if valid_voltage_tiers:
        voltage_tier = max(valid_voltage_tiers)
    else:
        _LOGGER.debug(f'No valid voltage tier found for machine {machine} and recipe {recipe_row.ID}. '
                      f'Recipe voltage tier: {base_recipe.voltage_tier}, '
                      f'default voltage tier: {default_voltage_tier}')
        voltage_tier = base_recipe.voltage_tier
    raw_recipe = machine.fit_recipe(raw_recipe=base_recipe, voltage_tier=voltage_tier)
    return Recipe(
        id=recipe_row.ID,
        base_recipe=base_recipe,
        raw_recipe=raw_recipe,
        valid_machines=recipe_row.MACHINES,
        machine=machine,
        cap=None,
        cap_specified=False
    )


def initialize_machine_options(database: GTNHDatabase) -> None:
    for machine in database.extracted_machines.values():
        for option_type in machine.machine_options.valid_options:
            options = database.machine_options_book.get_machine_option_list(
                option_type=option_type
            )
            if options:
                machine.machine_options.set_option(
                    option_type, min(options, key=lambda o: o.tier)
                )


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
                voltage_tiers={v for v in VoltageTier.valid_voltage_tiers() if v <= config.max_voltage_tier},
                machines={m for m in database.extracted_machines.values() if not m.disabled}
            )
            # df['MACHINES'] = df['MACHINES'].map(
            #     lambda machines: {m for m in machines if not m.unspecified})

            df = df[df['MACHINES'].map(len) > 0].drop(columns='TOTAL_EU').copy().reset_index()

            starting_materials = config.inputs | config.infinite_materials
            _LOGGER.info(f'Starting materials: {starting_materials}')
            initial_material_grading, df = database.get_reachable_recipes(df, starting_materials, sort=False)
            reachable_materials = {m.id: m for m, g in initial_material_grading.items() if g >= 0}
            _LOGGER.info(f'Reachable recipes: {df.shape[0]}')

            target_materials = list(config.outputs.union(config.inputs))
            _, df = database.get_ingredient_recipes(df, target_materials, sort=False)

            if df.shape[0] <= 0:
                raise ValueError(f'No recipes found for the specified config.')

            # Take the cross product of all input groups
            reachable_set = set(reachable_materials.values())
            rows = []
            for row in df.itertuples(index=False):
                input_groups = list(row.TOTAL_INPUTS.keys())
                amounts = list(row.TOTAL_INPUTS.values())
                material_lists = [g.materials for g in input_groups]

                for index, materials in enumerate(product(*material_lists)):
                    recipe_id = f"{row.ID}{index}"
                    inputs = {
                        k: (m, v[1]) for (k, v), m in zip(row.INPUT_GROUPS.items(), materials)
                    }
                    total_inputs = dict(zip(materials, amounts))
                    rows.append(
                        row._replace(ID=recipe_id, INPUT_GROUPS=inputs, TOTAL_INPUTS=total_inputs)._asdict()
                    )
                    for material in materials:
                        reachable_materials[material.id] = material
            df = pd.DataFrame(rows)

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
            initialize_machine_options(cc_database)

            recipes = {}
            for row in cc_database.df_recipes.itertuples(index=False):
                if row.SELECTED_MACHINE is None:
                    continue
                recipes[row.ID] = create_recipe_from_row(row, config.default_voltage_tier)

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
