from math import isnan
from dataclasses import dataclass
import pandas as pd
import logging
from typing import Dict, Iterable

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
