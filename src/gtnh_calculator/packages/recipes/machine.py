import logging
from email.contentmanager import raw_data_manager
from math import floor, log

from .voltage_tiers import VoltageTier
from .machine_options.machine_options import MachineOptions
from .raw_recipes import RawRecipe
from .machine_types import MachineType

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)
INFINITE_PERFECT_OVERCLOCKS = 1000


class Machine:
    machine_type: MachineType
    parallels: int
    voltage_tier: int
    machine_options: MachineOptions

    def __init__(
            self,
            machine_type: MachineType,
            voltage_tier: int,
            machine_options: MachineOptions
    ):
        self.machine_type = machine_type
        self.voltage_tier = voltage_tier if voltage_tier != VoltageTier.ULV else VoltageTier.LV
        self.machine_options = machine_options

    @property
    def name(self) -> str:
        return self.machine_type.name

    def __str__(self) -> str:
        option_string = self.machine_options.__str__()
        return f'{self.name} ({option_string})' if option_string != '' else self.name

    @property
    def voltage_tier_name(self) -> str:
        return VoltageTier.voltage_tier_name(self.voltage_tier)

    def maximal_perfect_overclocks(self, raw_recipe: RawRecipe) -> int:
        match self.machine_type.name:
            case 'Large Chemical Reactor':
                return INFINITE_PERFECT_OVERCLOCKS
            case 'Digester':
                return INFINITE_PERFECT_OVERCLOCKS
            case 'Blast Furnace':
                blast_furnace_temperature = (self.machine_options.coil.temperature +
                                             max((self.voltage_tier - VoltageTier.MV) * 100, 0))
                recipe_temperature = raw_recipe.recipe_options.temperature
                return max((blast_furnace_temperature - recipe_temperature) // 1800, 0)
            case _:
                return 0

    def _energy_discount_for_recipe(self, raw_recipe: RawRecipe) -> float:
        match self.machine_type.name:
            case 'Blast Furnace':
                blast_furnace_temperature = (self.machine_options.coil.temperature +
                                             max((self.voltage_tier - VoltageTier.MV) * 100, 0))
                recipe_temperature = raw_recipe.recipe_options.temperature

                return 0.95 ** max((blast_furnace_temperature - recipe_temperature) // 900, 0)
            case 'Oil Cracking Unit':
                return 1 - max(self.machine_options.coil.tier * 0.1, 0.5)
            case _:
                return 1

    def _speedup_for_recipe(self, raw_recipe: RawRecipe) -> float:
        """
        :param raw_recipe:
        :return: Speed boost, which both affects processing time and total EU cost.
        Result of 2 means half processing time
        """
        match self.machine_type.name:
            case 'Pyrolyse Oven':
                return 0.5 * self.machine_options.coil.tier
            case 'ExxonMobil Chemical Plant':
                return 0.5 * self.machine_options.coil.tier
            case _:
                return 1

    @property
    def max_parallels(self) -> int:
        if self.voltage_tier <= 0:
            return 1
        match self.machine_type.name:
            case 'ExxonMobil Chemical Plant':
                return 2 * self.machine_options.pipe_casing.tier
            case _:
                return self.machine_type.base_parallels + self.voltage_tier * self.machine_type.parallels_per_voltage_tier

    def fit_recipe(self, raw_recipe: RawRecipe) -> RawRecipe:
        if raw_recipe.total_eu > 0:
            # EU Generators cannot be overclocked
            return raw_recipe

        _LOGGER.debug(f'Before: {raw_recipe}')
        base_voltage_tier = raw_recipe.base_voltage_tier
        energy_discount = self._energy_discount_for_recipe(raw_recipe)
        max_parallels = self.max_parallels

        max_eu_per_tick = VoltageTier.eu_per_tick(self.voltage_tier)
        reduced_eu_per_tick = abs(energy_discount * raw_recipe.eu_per_tick)
        if reduced_eu_per_tick > 0:
            used_parallels = min(floor(max_eu_per_tick // reduced_eu_per_tick), max_parallels)
            overclocks = floor(log(max_eu_per_tick // (used_parallels * reduced_eu_per_tick), 4))
        else:
            used_parallels = max_parallels
            overclocks = 0

        perfect_overclocks = min(self.maximal_perfect_overclocks(raw_recipe), overclocks)
        speedup = self._speedup_for_recipe(raw_recipe)

        total_eu = (raw_recipe.total_eu * energy_discount * self.machine_type.energy_multiplier * used_parallels *
                    2 ** (overclocks - perfect_overclocks) / speedup)
        processing_time = (raw_recipe.processing_time / speedup /
                           (4 ** perfect_overclocks * 2 ** (overclocks - perfect_overclocks)))
        recipe_materials = {
            m: (used_parallels * a if m.id != 0 else total_eu) for m, a in raw_recipe.materials.items()
        }

        match self.machine_type.name:
            case 'ExxonMobil Chemical Plant':
                catalyst_names = [
                    'Green Metal Catalyst', 'Red Metal Catalyst', 'Yellow Metal Catalyst',
                    'Blue Metal Catalyst', 'Orange Metal Catalyst', 'Purple Metal Catalyst', 'Brown Metal Catalyst',
                    'Pink Metal Catalyst', 'Formaldehyde Catalyst', 'Solid-Acid Catalyst', 'Infinite Mutation Catalyst'
                ]
                if self.machine_options.pipe_casing.tier >= 4 and self.machine_options.coil.tier >= 11:
                    recipe_materials = {m: a for m, a in recipe_materials.items() if m.name not in catalyst_names}
                else:
                    catalyst_consumption = 1 - 0.2 * self.machine_options.pipe_casing.tier
                    recipe_materials = {m: (catalyst_consumption if m.name in catalyst_names else a)
                                        for m, a in recipe_materials.items()}


        _LOGGER.debug((VoltageTier.voltage_tier_name(base_voltage_tier), VoltageTier.voltage_tier_name(self.voltage_tier)))
        _LOGGER.debug(f'Used_parallels: {used_parallels}, overclocks: {overclocks}, perfect_overclocks: {perfect_overclocks}')
        new_raw_recipe = RawRecipe(
            materials=recipe_materials, processing_time=processing_time, recipe_options=raw_recipe.recipe_options
        )
        _LOGGER.debug(f'Machine: {self}')
        _LOGGER.debug(f'Machine Options: {self.machine_options.__repr__()}')
        _LOGGER.debug(f'After : {new_raw_recipe}\n')

        return new_raw_recipe
