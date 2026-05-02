from __future__ import annotations
import logging
from typing import cast
import yaml
from itertools import product as cross_product

from .machine_options import *
from ..machine_types import MachineType
from ..raw_recipes import RawRecipe

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class MachineOptionsBook:
    coils: list[Coil]
    pipe_casings: list[PipeCasing]
    item_pipe_casings: list[ItemPipeCasing]
    electromagnets: list[Electromagnet]
    solenoid_coils: list[SolenoidCoil]
    anvils: list[Anvil]

    @property
    def all_options(self) -> list[MachineOption]:
        return self.coils + self.pipe_casings

    def get_coil(self, input_string: str) -> Coil | None:
        return self._get_machine_option(input_string, self.coils)

    def get_pipe_casing(self, input_string: str) -> PipeCasing | None:
        return self._get_machine_option(input_string, self.pipe_casings)

    def get_item_pipe_casing(self, input_string: str) -> ItemPipeCasing | None:
        return self._get_machine_option(input_string, self.item_pipe_casings)

    def get_electromagnet(self, input_string: str) -> Electromagnet | None:
        return self._get_machine_option(input_string, self.electromagnets)

    def get_solenoid_coil(self, input_string: str) -> SolenoidCoil | None:
        return self._get_machine_option(input_string, self.solenoid_coils)

    def get_anvil(self, input_string: str) -> Anvil | None:
        return self._get_machine_option(input_string, self.anvils)

    def get_machine_option(self, input_string: str) -> MachineOption | None:
        return self._get_machine_option(input_string, self.all_options)

    def get_machine_option_list(
        self,
        option_type: str,
        minimum: MachineOption | None,
        maximum: MachineOption | None
    ) -> list[MachineOption]:
        options = getattr(self, option_type)
        if minimum is None:
            minimum = options[0]
        if maximum is None:
            maximum = options[-1]
        return [o for o in options if minimum <= o <= maximum]

    @staticmethod
    def _get_machine_option(input_string: str, options: list[MachineOption]) -> MachineOption | None:
        for option in options:
            if option.fits(input_string):
                return option
        _LOGGER.warning(f'No Machine Option "{input_string}" found.')
        return None

    def get_machine_options_from_string(self, input_string: str) -> MachineOptions:
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

    def get_default_options(
        self,
        raw_recipe: RawRecipe,
        machine_type: MachineType,
        config_default: MachineOptions,
    ) -> MachineOptions:
        def default_options() -> MachineOptions:
            match machine_type.name:
                case 'Blast Furnace':
                    return MachineOptions(coil=self.get_minimal_coil(raw_recipe.recipe_options.temperature))
                case 'ExxonMobil Chemical Plant':
                    return MachineOptions(coil=self.coils[0], pipe_casing=self.pipe_casings[0])
                case 'Magnetic Flux Exhibitor':
                    return MachineOptions(electromagnet=self.electromagnets[0])
                case 'Oil Cracking Unit':
                    return MachineOptions(coil=self.coils[0])
                case 'Pyrolyse Oven':
                    return MachineOptions(coil=self.coils[0])
                case 'Volcanus':
                    return MachineOptions(coil=self.coils[0])
                case _:
                    return MachineOptions()

        machine_options = default_options()

        """
            Update machine options to specified default
        """

        for attr, value in vars(machine_options).items():
            if value is not None:
                setattr(
                    machine_options, attr,
                    MachineOption.maximum(
                        getattr(machine_options, attr),
                        getattr(config_default, attr)
                    )
                )

        if machine_options.coil is not None:
            if machine_type.name == 'Oil Cracking Unit' and machine_options.coil.tier > 5:
                machine_options.coil = self.coils[4]
        return machine_options

    def all_option_combinations(
        self,
        machine_type: MachineType,
        config_default: MachineOptions,
        config_maximum: MachineOptions,
        voltage_tiers: list[int]
    ) -> list[tuple[MachineOptions, int]]:
        """
        Currently unused
        :param machine_type:
        :param config_default:
        :param config_maximum:
        :param voltage_tiers:
        :return:
        """
        sets = [
                   self.get_machine_option_list(t, getattr(config_default, t[:-1]), getattr(config_maximum, t[:-1]))
                   for t in machine_type.valid_machine_options
               ] + [voltage_tiers]

        result = []
        for options in cross_product(*sets):
            result.append(
                (MachineOptions.create_options_from(options[:-1]), options[-1])
            )
        return result

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
    item_pipe_casings = fields.List(fields.Nested(ItemPipeCasingSchema, required=True), required=True)
    electromagnets = fields.List(fields.Nested(ElectromagnetSchema, required=True), required=True)
    solenoid_coils = fields.List(fields.Nested(SolenoidCoilSchema, required=True), required=True)
    anvils = fields.List(fields.Nested(AnvilSchema, required=True), required=True)

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
