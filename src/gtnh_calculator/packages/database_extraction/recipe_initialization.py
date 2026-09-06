import pandas as pd
import logging
from typing import Dict, Iterable
from dataclasses import dataclass
from math import isnan
from collections import defaultdict

from ..recipes_db.adapted_recipes import AdaptedRecipe, InvalidAdaptedRecipe
from ..recipes_db.recipes import Recipe, get_id
from ..recipes_db.instantiated_recipes import InstantiatedRecipe, RecipeEnvironment
from ..recipes_db.recipe_options import RecipeOptions
from ..recipes_db.machine_options.machine_options import MachineOptions
from ..recipes_db.machine_options.machine_option_books import MachineOptionsBook
from ..recipes_db.machines import Machine
from ..recipes_db.raw_recipes import InputCombination
from ..recipes_db.voltage_tiers import VoltageTier
from ..recipes_db.behaviours.machine_behaviours import FittingContext
from ..configs.crafting_chain_config_db import CraftingChainConfig
from ..streamlit.session_state import StoredRecipeEnvironment

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


@dataclass
class RecipeInitializer:
    machine_options_book: MachineOptionsBook

    def get_base_machines(
        self, recipe: Recipe, default_voltage_tier: int | None = None, max_voltage_tier: int | None = None
    ) -> list[Machine]:
        max_voltage_tier = VoltageTier.MAX if max_voltage_tier is None else max_voltage_tier
        machines = sorted([(m, min(m.machine_stats.voltage_tiers)) for m in recipe.valid_machines], key=lambda x: x[1])
        lv_machines, hv_machines = [], []
        for machine, min_voltage_tier in machines:
            if default_voltage_tier is None or min_voltage_tier <= default_voltage_tier:
                lv_machines.append(machine)
            elif default_voltage_tier is None or min_voltage_tier <= max_voltage_tier:
                hv_machines.append(machine)
        groups = defaultdict(set)

        def add_to_group(machine):
            if not isnan(recipe_options.fusion_tier) and machine.machine_stats.fusion_tier < recipe_options.fusion_tier:
                return
            if not isnan(recipe_options.coil_heat) and (self.machine_options_book.max_coil_heat(machine) < recipe_options.coil_heat):
                return
            groups[(frozenset(machine.machine_types), machine.multiblock)].add(machine)

        recipe_options = recipe.recipe_options
        for machine in lv_machines:
            add_to_group(machine)

        # If no machines were found, also add higher voltage machines
        if all(len(groups[g]) == 0 for g in groups.keys()):
            for machine in hv_machines:
                add_to_group(machine)

        voltage_tier_sign = 1 if default_voltage_tier is None else -1
        if not isnan(recipe_options.fusion_tier):
            key = lambda m: (m.weight, m.machine_stats.fusion_tier, voltage_tier_sign * m.minimal_voltage_tier())
        else:
            key = lambda m: (m.weight, voltage_tier_sign * m.minimal_voltage_tier())
        
        base_machines = [min(group, key=key) for group in groups.values()]
        if not base_machines:
            _LOGGER.debug(f'No base machines found. Machine groups: '
                            f'{[(t, [(m.name, m.voltage_tiers) for m in g]) for t, g in groups.items()]}')
            
        # if recipe_row.ID == 'r~05TjouNsODuqZ5mSy0oojg==':
        #     _LOGGER.warning(f'Processing recipe: {recipe_row}')
        #     _LOGGER.warning(f'lv_machines: {lv_machines}')
        #     _LOGGER.warning(f'hv_machines: {hv_machines}')
        #     _LOGGER.warning(f'groups: {groups}')
        #     _LOGGER.warning(f'base_machines: {base_machines}')
        return base_machines

    def get_default_machine_and_voltage_tier(
        self, recipe: Recipe, default_voltage_tier: int | None = None, max_voltage_tier: int | None = None, 
        prefer_singleblocks: bool = True
    ) -> tuple[Machine | None, int]:
        def base_voltage_tier(machine: Machine) -> int:
            valid_voltage_tiers = [v for v in machine.voltage_tiers if recipe.voltage_tier <= v]
            if not valid_voltage_tiers:
                raise ValueError(f'No valid voltage tier found for machine {machine} and recipe {recipe}. '
                                f'Default voltage tier: {default_voltage_tier}')

            if default_voltage_tier is None:
                return min(valid_voltage_tiers)
            else:
                valid_low_voltage_tiers = [v for v in valid_voltage_tiers if v <= default_voltage_tier]
                return max(valid_low_voltage_tiers) if valid_low_voltage_tiers else min(valid_voltage_tiers)

        base_machines = self.get_base_machines(recipe, default_voltage_tier, max_voltage_tier)
        if prefer_singleblocks and not all(m.multiblock for m in base_machines):
            base_machines = [m for m in base_machines if not m.multiblock]

        base_machine_names = [m.name for m in base_machines]
        if 'Large Chemical Reactor' in base_machine_names and 'Mega Chemical Reactor' in base_machine_names:
            base_machines = [m for m in base_machines if m.name != 'Mega Chemical Reactor']
        if 'Large Scale Auto-Assembler v1.01' in base_machine_names and 'Precise Auto-Assembler MT-3662' in base_machine_names:
            base_machines = [m for m in base_machines if m.name != 'Precise Auto-Assembler MT-3662']
        if 'Dangote Distillus' in base_machine_names and 'Mega Distillation Tower' in base_machine_names:
            base_machines = [m for m in base_machines if m.name != 'Mega Distillation Tower']
        if 'Distillation Tower' in base_machine_names and 'Dangote Distillus' in base_machine_names:
            base_machines = [m for m in base_machines if m.name != 'Dangote Distillus']
        if 'Neutronium Compressor' in base_machine_names and 'Pseudostable Black Hole Containment Field' in base_machine_names:
            base_machines = [m for m in base_machines if m.name != 'Pseudostable Black Hole Containment Field']

        if not base_machines:
            _LOGGER.warning(f'No default machine: {base_machines} | {recipe}. \n'
                        f'Machines: {[(m.name, m.voltage_tiers) for m in recipe.valid_machines]}')
            return None, VoltageTier.NO_REQUIREMENT
        
        # if 'Superdense Magnetohydrodynamically Constrained Star Matter Plate' in [m.name for m in
        #                                                                           recipe_row.AVG_OUTPUTS.keys()]:
        #     machine = [m for m in base_machines if m.name == 'Pseudostable Black Hole Containment Field'][0]
        #     return machine, base_voltage_tier(machine)
        
        machine = min(base_machines, key=lambda m: m.weight)
        return machine, base_voltage_tier(machine)

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
            valid_options=machine.valid_options,
            options=selected_options,
            min_tier={t: -1 for t in machine.valid_options}
        )

    def adapt_recipe(self, recipe: Recipe, recipe_environment: RecipeEnvironment) -> AdaptedRecipe:
        adapted_recipe = None
        try:
            for v in range(recipe_environment.voltage_tier, VoltageTier.MAX + 1):
                try:
                    adapted_recipe = recipe_environment.machine.machine_behaviour.fit_recipe(FittingContext(
                        raw_recipe=recipe.raw_recipe,
                        voltage_tier=v,
                        machine_stats=recipe_environment.machine.machine_stats,
                        machine_options=recipe_environment.machine_options
                    ))
                except ValueError as e:
                    raise ValueError(f'Error occurred while fitting recipe {recipe.raw_recipe} to machine {recipe_environment.machine}. VT: {recipe_environment.voltage_tier}: {e}')
                if adapted_recipe is None or adapted_recipe.used_parallels > 0 or recipe_environment.voltage_tier == VoltageTier.NO_REQUIREMENT:
                    break
                
                # Only continue if raising the voltage tier would allow for parallels
                max_parallels = recipe_environment.machine.machine_behaviour.parallel_behaviour.get_parallels(
                    voltage_tier=recipe_environment.voltage_tier,
                    machine_options=recipe_environment.machine_options
                )
                if max_parallels != 0 or recipe_environment.machine.machine_behaviour.parallel_behaviour.parallels_per_voltage_tier == 0:
                    break
        except TypeError as e:
            raise TypeError(f'TypeError occurred while fitting recipe {recipe.raw_recipe} to machine {recipe_environment.machine}. VT: {recipe_environment.voltage_tier}, {type(recipe_environment.voltage_tier)}: {e}')

        if adapted_recipe is None:
            _LOGGER.warning(f'Could not fit recipe {recipe.raw_recipe} to machine {recipe_environment.machine} with voltage tier {recipe_environment.voltage_tier}')
            return InvalidAdaptedRecipe()
        return adapted_recipe
    
    def instantiate_recipes_from_raw(self, df_recipes: pd.DataFrame, pick_any: bool = False) -> Dict[str, InstantiatedRecipe]:
        """
        Instantiation without config and without changed recipe environments.
        """
        instantiated_recipes: Dict[str, InstantiatedRecipe] = {}
        for row in df_recipes.itertuples(index=False):
            if row.SELECTED_MACHINE is None:
                continue
            recipe: Recipe = row.RECIPE  # type: ignore
            machine: Machine = row.SELECTED_MACHINE  # type: ignore
            voltage_tier: int = row.SELECTED_VOLTAGE_TIER  # type: ignore
            machine_options = self.create_default_machine_options(machine, recipe.raw_recipe.recipe_options)

            # Take the cross product of all input groups
            for instance_number, input_combination in enumerate(recipe.input_combinations(pick_any=pick_any)):
                recipe_environment = RecipeEnvironment(
                    machine=machine,
                    voltage_tier=voltage_tier,
                    machine_options=machine_options
                )
                adapted_recipe = self.adapt_recipe(recipe, recipe_environment)
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

    def instantiate(
        self, recipe: Recipe, config: CraftingChainConfig, pick_any: bool = False, 
        input_combinations: list[InputCombination] | None = None,
        changed_recipe_environments: Dict[str, tuple[RecipeEnvironment, StoredRecipeEnvironment]] = {}
    ) -> list[InstantiatedRecipe]:
        """
        Used for lazy evaluation (only call when needed)
        """
        machine, voltage_tier = self.get_default_machine_and_voltage_tier(
            recipe, config.default_voltage_tier, config.max_voltage_tier, prefer_singleblocks=True)
        if machine is None:
            _LOGGER.warning(f'Could not determine the default machine for recipe: {recipe}')
            return []
        machine_options = self.create_default_machine_options(machine, recipe.raw_recipe.recipe_options)
        if input_combinations is None:
            input_combinations = recipe.input_combinations(pick_any=pick_any)
        else:
            input_combinations = [input_combinations[0]] if pick_any and input_combinations else input_combinations

        instantiated_recipes = []
        for input_combination in input_combinations:
            id = get_id(recipe.id, input_combination.instance_number)
            if id in changed_recipe_environments.keys():
                recipe_environment = changed_recipe_environments[id][1].to_environment()
                _LOGGER.info(f'Using changed recipe environment for recipe {id}: {recipe_environment}')
            else:
                recipe_environment = RecipeEnvironment(
                    machine=machine,
                    voltage_tier=voltage_tier,
                    machine_options=machine_options
                )
            adapted_recipe = self.adapt_recipe(recipe, recipe_environment)
            instantiated_recipes.append(InstantiatedRecipe(
                instance_number=input_combination.instance_number,
                base_recipe=recipe,
                adapted_recipe=adapted_recipe,
                recipe_environment=recipe_environment,
                input_combination=input_combination,
                cap=None,
                cap_specified=False
            ))
        return instantiated_recipes
        
    def instantiate_all(
        self, df_recipes: pd.DataFrame, config: CraftingChainConfig, pick_any: bool = False,
        changed_recipe_environments: Dict[str, tuple[RecipeEnvironment, StoredRecipeEnvironment]] = {}
    ) -> Dict[str, InstantiatedRecipe]:
        instantiated_recipes = {}
        for recipe_row in df_recipes.itertuples(index=False):
            recipe: Recipe = recipe_row.RECIPE  # type: ignore
            for instantiated_recipe in self.instantiate(
                recipe, config=config, pick_any=pick_any, changed_recipe_environments=changed_recipe_environments):
                instantiated_recipes[instantiated_recipe.id] = instantiated_recipe
        return instantiated_recipes
