from __future__ import annotations
from dataclasses import dataclass
import logging
from typing import Dict
from math import nan

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class RecipeOptions:
    options: Dict[str, float]

    @classmethod
    def get_recipe_options(cls, metadata: Dict[str, float]) -> RecipeOptions:
        return RecipeOptions(options=metadata)

    @property
    def temperature(self) -> float:
        if 'temperature' in self.options:
            return self.options['temperature']
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
