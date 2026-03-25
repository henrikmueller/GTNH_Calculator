from __future__ import annotations
from dataclasses import dataclass
import logging

from ..utility.general_utility import str_to_float

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class RecipeOptions:
    temperature: int | None

    @classmethod
    def get_recipe_options(cls, input_string: str) -> RecipeOptions:
        recipe_options = RecipeOptions.create_empty_options()
        # TODO
        return recipe_options

    @classmethod
    def create_empty_options(cls) -> RecipeOptions:
        return RecipeOptions(
            temperature=None
        )

    def markdown_string(self) -> str:
        result = []
        if self.temperature is not None:
            result.append(f'**Temperature**: {self.temperature} K')
        return ', '.join(result)
