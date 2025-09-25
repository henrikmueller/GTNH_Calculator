from __future__ import annotations
from dataclasses import dataclass
import logging
import yaml
from marshmallow import Schema, fields, post_load

from .machine_options import (
    MachineOption, MachineOptions, Coil, CoilSchema, PipeCasing, PipeCasingSchema
)
from ..machine_types import MachineType
from ..raw_recipes import RawRecipe

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class MachineOptionsBook:
    coils: list[Coil]
    pipe_casings: list[PipeCasing]

    @property
    def all_options(self) -> list[MachineOption]:
        return self.coils + self.pipe_casings

    def get_coil(self, input_string: str) -> Coil | None:
        return self._get_machine_option(input_string, self.coils)

    def get_machine_option(self, input_string: str) -> MachineOption | None:
        return self._get_machine_option(input_string, self.all_options)

    @staticmethod
    def _get_machine_option(input_string: str, options: list[MachineOption]) -> MachineOption | None:
        for option in options:
            if option.fits(input_string):
                return option
        _LOGGER.warning(f'No Machine Option "{input_string}" found.')
        return None

    def get_machine_options(self, input_string: str) -> MachineOptions:
        if input_string == '':
            return MachineOptions.create_empty_options()
        options = []
        for raw_option in input_string.split(','):
            option = self.get_machine_option(raw_option.strip())
            if option is not None:
                options.append(option)

        machine_options = MachineOptions.create_empty_options()
        for option in options:
            machine_options.set_option(option)
        return machine_options

    def get_default_options(self, raw_recipe: RawRecipe, machine_type: MachineType) -> MachineOptions:
        match machine_type.name:
            case 'Blast Furnace':
                return MachineOptions(coil=self.get_minimal_coil(raw_recipe.recipe_options.temperature))
            case 'Pyrolyse Oven':
                return MachineOptions(coil=self.coils[0])
            case 'Oil Cracking Unit':
                return MachineOptions(coil=self.coils[0])
            case _:
                return MachineOptions()

    def get_minimal_coil(self, recipe_temperature: int | None) -> Coil | None:
        if recipe_temperature is None:
            return None
        # Works, since the coils list is sorted
        for coil in self.coils:
            if coil.temperature >= recipe_temperature:
                return coil
        return None


class MachineOptionsBookSchema(Schema):
    coils = fields.List(fields.Nested(CoilSchema, required=True), required=True)
    pipe_casings = fields.List(fields.Nested(PipeCasingSchema, required=True), required=True)

    @post_load
    def create(self, data, **kwargs) -> MachineOptionsBook:
        machine_options_book = MachineOptionsBook(**data)
        machine_options_book.coils.sort(key=lambda c: c.tier)
        return machine_options_book


def load_possible_machine_options(path: str) -> MachineOptionsBook:
    with open(path, 'r') as f:
        yaml_data = yaml.load(f, Loader=yaml.SafeLoader)
        schema = MachineOptionsBookSchema()
        return schema.load(yaml_data)
