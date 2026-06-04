from math import isnan
from dataclasses import dataclass
import pandas as pd
import logging
from typing import Dict, Iterable
from collections import defaultdict

from ..recipes_db.material import Material
from ..recipes_db.machines import Machine
from ..recipes_db.recipes import Recipe
from ..recipes_db.voltage_tiers import VoltageTier
from ..recipes_db.machine_options.machine_option_books import MachineOptionsBook
from ..recipes_db.recipe_options import RecipeOptionType
from ..utility.constants import GT_EU_KEY, INCLUDE_DEPRECATED_MACHINES

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


@dataclass
class GTNHDatabase:
    df_recipes: pd.DataFrame
    extracted_materials: Dict[str, Material]
    extracted_machines: Dict[str, Machine]
    machine_options_book: MachineOptionsBook
    includes_deprecated_machines: bool = INCLUDE_DEPRECATED_MACHINES

    def mod_set_materials(self) -> set[str]:
        return set(m.mod for m in self.extracted_materials.values())

    def mod_set_recipes(self) -> set[str]:
        return set(set(self.df_recipes["RECIPE"].apply(lambda r: r.category)))

    def add_eu(self) -> None:
        if GT_EU_KEY in self.extracted_materials.keys():
            raise AssertionError(f'{GT_EU_KEY} must not a key of material.')
        self.extracted_materials[GT_EU_KEY] = Material(
            id=GT_EU_KEY,
            image_file_path='',
            name='EU',
            mod='gregtech',
            nbt='',
            tooltip='The Electric Unit, the standard unit of energy in GTNH.'
        )

    def filter_recipes(
        self,
        df_recipes: pd.DataFrame,
        excluded_ids: set[str] | frozenset[str] | None = None,
        inputs: Iterable[Material] | None = None,
        outputs: Iterable[Material] | None = None,
        outputs_any: Iterable[Material] | None = None,
        excluded_outputs: Iterable[Material] | None = None,
        voltage_tiers: set[int] | frozenset[int] | None = None,
        categories: Iterable[str] | None = None,
        allowed_machines: set[Machine] | frozenset[Machine] | None = None,
        recipe_options: Iterable[RecipeOptionType] | None = None
    ) -> pd.DataFrame:
        df_result = df_recipes.copy(deep=False)

        if excluded_ids is not None:
            df_result = df_result[~df_result['ID'].isin(excluded_ids)]
        if inputs is not None:
            df_result = df_result[df_result['RECIPE'].map(lambda r: all(
                any(input in input_group.materials for input_group in r.inputs) for input in inputs)
            )]
        if outputs is not None:
            df_result = df_result[df_result['RECIPE'].map(lambda r: all(
                output in r.outputs for output in outputs
            ))]
        if outputs_any is not None:
            df_result = df_result[df_result['RECIPE'].map(lambda r: any(
                output in r.outputs for output in outputs_any
            ))]
        if excluded_outputs is not None:
            df_result = df_result[df_result['RECIPE'].map(lambda r: all(
                output not in excluded_outputs for output in r.outputs
            ))]
        if voltage_tiers is not None:
            min_vt, max_vt = min(voltage_tiers), max(voltage_tiers)
            if voltage_tiers and max_vt - min_vt + 1 == len(voltage_tiers):
                df_result = df_result[df_result['RECIPE'].map(lambda r: 
                    r.voltage_tier >= min_vt and r.voltage_tier <= max_vt)]
            else:
                df_result = df_result[df_result['RECIPE'].map(lambda r: 
                    r.voltage_tier in voltage_tiers)]
        if categories is not None:
            df_result = df_result[df_result['RECIPE'].map(lambda r: 
                r.category in categories)]
        if allowed_machines is not None:
            df_result = df_result[df_result['RECIPE'].map(lambda r: bool(r.valid_machines & allowed_machines))]
        if recipe_options is not None:
            df_result = df_result[df_result['RECIPE'].map(lambda r: 
                all(r.recipe_options.has_option(option) for option in recipe_options))]
        return df_result

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
        self, recipe_row, default_voltage_tier: int | None = None, max_voltage_tier: int | None = None, 
        prefer_singleblocks: bool = True
    ) -> tuple[Machine | None, int]:
        recipe: Recipe = recipe_row.RECIPE

        def base_voltage_tier(machine: Machine) -> int:
            valid_voltage_tiers = [v for v in machine.voltage_tiers if recipe.voltage_tier <= v]
            if not valid_voltage_tiers:
                raise ValueError(f'No valid voltage tier found for machine {machine} and recipe {recipe_row}. '
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
            _LOGGER.warning(f'No default machine: {base_machines} | {recipe_row}. \n'
                        f'Machines: {[(m.name, m.voltage_tiers) for m in recipe_row.MACHINES]}')
            return None, VoltageTier.NO_REQUIREMENT
        
        # if 'Superdense Magnetohydrodynamically Constrained Star Matter Plate' in [m.name for m in
        #                                                                           recipe_row.AVG_OUTPUTS.keys()]:
        #     machine = [m for m in base_machines if m.name == 'Pseudostable Black Hole Containment Field'][0]
        #     return machine, base_voltage_tier(machine)
        
        machine = min(base_machines, key=lambda m: m.weight)
        return machine, base_voltage_tier(machine)
