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
    TEMPERATURE = 'temperature'
    FUSION_TIER = 'fusion_tier'


@dataclass
class RecipeOptions:
    options: Dict[str, float]

    @classmethod
    def get_recipe_options(cls, metadata: Dict[str, float], additional_info: str) -> RecipeOptions:
        options = {}
        if additional_info:
            match = re.match(r"^To start: .*? EU \(MK (.*?)\)$", additional_info)
            if match:
                options[RecipeOptionType.FUSION_TIER] = str_to_float(match.group(1))
        return RecipeOptions(options=metadata | options)

    @property
    def fusion_tier(self) -> float:
        if RecipeOptionType.FUSION_TIER in self.options.keys():
            return self.options[RecipeOptionType.FUSION_TIER]
        return nan

    @property
    def temperature(self) -> float:
        if RecipeOptionType.TEMPERATURE in self.options.keys():
            return self.options[RecipeOptionType.TEMPERATURE]
        return nan

    def markdown_string(self) -> str:
        result = []
        if self.temperature is not None:
            result.append(f'**Temperature**: {self.temperature} K')
        return ', '.join(result)

    def __repr__(self):
        if not self.options:
            return 'RecipeOptions: None'
        return f'RecipeOptions: {', '.join(f"{k}: {v}" for k, v in self.options.items())}'

    def __bool__(self):
        return len(self.options) > 0
