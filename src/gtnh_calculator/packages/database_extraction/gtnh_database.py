from math import isnan
from dataclasses import dataclass
import pandas as pd
import logging
from typing import Dict, Iterable
from collections import defaultdict
from itertools import product

from ..recipes_db.material import Material
from ..recipes_db.machines import Machine
from ..recipes_db.machine_options.machine_option_books import MachineOptionsBook
from ..recipes_db.recipe_options import RecipeOptions
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
        return set(self.df_recipes['CATEGORY'].unique())

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
        inputs: set[Material] | None = None,
        outputs: set[Material] | None = None,
        excluded_outputs: set[Material] | None = None,
        voltage_tiers: set[int] | None = None,
        categories: Iterable[str] | None = None,
        machines: set[Machine] | None = None,
        allowed_machines: set[Machine] | None = None
    ) -> pd.DataFrame:
        df_result = df_recipes.copy(deep=False)
        if inputs is not None:
            df_result = df_result[df_result['TOTAL_INPUTS'].map(lambda input_groups: all(
                any(input in input_group.materials for input_group in input_groups) for input in inputs
            ))]
        if outputs is not None:
            df_result = df_result[df_result['AVG_OUTPUTS'].map(lambda avg_outputs: all(
                output in avg_outputs.keys() for output in outputs
            ))]
        if excluded_outputs is not None:
            df_result = df_result[df_result['AVG_OUTPUTS'].map(lambda avg_outputs: all(
                output not in excluded_outputs for output in avg_outputs.keys()
            ))]
        if voltage_tiers is not None:
            if voltage_tiers and max(voltage_tiers) - min(voltage_tiers) + 1 == len(voltage_tiers):
                df_result = df_result[(df_result['VOLTAGE_TIER'] >= min(voltage_tiers)) &
                                       (df_result['VOLTAGE_TIER'] <= max(voltage_tiers))]
            else:
                df_result = df_result[df_result['VOLTAGE_TIER'].isin(voltage_tiers)]
        if categories is not None:
            df_result = df_result[df_result['CATEGORY'].isin(categories)]
        if machines is not None:
            df_result['MACHINES'] = df_result['MACHINES'].map(lambda s: s & machines)
            df_result = df_result[df_result['MACHINES'].map(len) > 0]
        if allowed_machines is not None:
            df_result = df_result[df_result['MACHINES'].map(lambda s: bool(s & allowed_machines))]
        return df_result

    def get_base_machines(self, recipe_row, default_voltage_tier: int | None = None) -> list[Machine]:
        groups = defaultdict(set)
        recipe_options = recipe_row.RECIPE_OPTIONS
        for machine in recipe_row.MACHINES:
            if not isnan(recipe_options.fusion_tier) and machine.machine_stats.fusion_tier < recipe_options.fusion_tier:
                continue
            if not isnan(recipe_options.coil_heat) and (self.machine_options_book.max_coil_heat(machine) < recipe_options.coil_heat):
                continue

            groups[(frozenset(machine.machine_types), machine.multiblock)].add(machine)
            # for voltage_tier in machine.voltage_tiers:
            #     if default_voltage_tier is None or voltage_tier <= default_voltage_tier:
            #         groups[(frozenset(machine.machine_types), machine.multiblock)].add(machine)
            #         break
        
        voltage_tier_sign = 1 if default_voltage_tier is None else -1
        if not isnan(recipe_options.fusion_tier):
            key = lambda m: (m.weight, m.machine_stats.fusion_tier, voltage_tier_sign * m.minimal_voltage_tier())
        else:
            key = lambda m: (m.weight, voltage_tier_sign * m.minimal_voltage_tier())
                    
        base_machines = [min(group, key=key) for group in groups.values()]
        if not base_machines:
            _LOGGER.debug(f'No base machines found. Machine groups: '
                            f'{[(t, [(m.name, m.voltage_tiers) for m in g]) for t, g in groups.items()]}')
        return base_machines

    def get_default_machine(self, recipe_row, default_voltage_tier: int | None = None) -> Machine | None:
        base_machines = self.get_base_machines(recipe_row, default_voltage_tier)
        if not all(m.multiblock for m in base_machines):
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

        if len(base_machines) == 1:
            return base_machines[0]
        if 'Superdense Magnetohydrodynamically Constrained Star Matter Plate' in [m.name for m in
                                                                                  recipe_row.AVG_OUTPUTS.keys()]:
            return [m for m in base_machines if m.name == 'Pseudostable Black Hole Containment Field'][0]

        _LOGGER.warning(f'No default machine: {base_machines} | {recipe_row}. \n'
                      f'Machines: {[(m.name, m.voltage_tiers) for m in recipe_row.MACHINES]}')
        return None
    
    @staticmethod
    def blow_up_input_groups(df_recipes: pd.DataFrame, pick_any: bool = False) -> pd.DataFrame:
        rows = []
        for row in df_recipes.itertuples(index=False):
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
                if pick_any:
                    break
        return pd.DataFrame(rows)
