from __future__ import annotations
from dataclasses import dataclass
import logging
from typing import Dict
from enum import StrEnum
from math import nan
import re

from ..utility.general_utility import str_to_float

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


class RecipeOptionType(StrEnum):
    COIL_HEAT = 'coil_heat'
    FUSION_TIER = 'fusion_tier'


@dataclass
class RecipeOptions:
    options: Dict[str, float]

    @classmethod
    def get_recipe_options(cls, recipe_row) -> RecipeOptions:
        options = recipe_row.METADATA
        if recipe_row.ADDITIONAL_INFO:
            match = re.match(r"^To start: .*? EU \(MK (.*?)\)$", recipe_row.ADDITIONAL_INFO)
            if match:
                options[RecipeOptionType.FUSION_TIER] = str_to_float(match.group(1))

            match = re.match(r"^Heat capacity: (.*?)K \(.*?\).*?$", recipe_row.ADDITIONAL_INFO)
            if match:
                coil_heat = str_to_float(match.group(1).replace(',', ''))
                if RecipeOptionType.COIL_HEAT in options.keys() and options[RecipeOptionType.COIL_HEAT] != coil_heat:
                    _LOGGER.warning(f'Different coil heat specifications from metadata ({recipe_row.METADATA} -> {options[RecipeOptionType.COIL_HEAT]}) '
                                    f'and additional info ({recipe_row.ADDITIONAL_INFO} -> {coil_heat}). Using the specification from additional info.')
                options[RecipeOptionType.COIL_HEAT] = coil_heat
        return RecipeOptions(options=options)

    @property
    def fusion_tier(self) -> float:
        if RecipeOptionType.FUSION_TIER in self.options.keys():
            return self.options[RecipeOptionType.FUSION_TIER]
        return nan

    @property
    def coil_heat(self) -> float:
        if RecipeOptionType.COIL_HEAT in self.options.keys():
            return self.options[RecipeOptionType.COIL_HEAT]
        return nan
    
    def has_option(self, option_type: RecipeOptionType) -> bool:
        return option_type in self.options.keys()

    def markdown_string(self) -> str:
        result = []
        if self.coil_heat is not None:
            result.append(f'**Coil Heat**: {self.coil_heat} K')
        return ', '.join(result)

    def __repr__(self):
        if not self.options:
            return 'RecipeOptions: None'
        return f'RecipeOptions: {', '.join(f"{k}: {v}" for k, v in self.options.items())}'

    def __bool__(self):
        return len(self.options) > 0
