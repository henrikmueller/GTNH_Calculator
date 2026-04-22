from __future__ import annotations
import logging
from dataclasses import dataclass

from .material import Material
from .voltage_tiers import VoltageTier
from .machine_options.machine_options import MachineOption
from .machine_options.machine_option_types import MachineOptionType
from .behaviours.machine_behaviours import MachineBehaviour
from .raw_recipes import RawRecipe

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


@dataclass
class Machine:
    name: str
    multiblock: bool
    deprecated: bool
    disabled: bool
    unspecified: bool
    voltage_tiers: list[int]
    _voltage_tier: int
    item: Material
    weight: int
    machine_behaviour: MachineBehaviour
    machine_types: set[MachineType]
    valid_options: list[MachineOptionType]
    speedup: float = 1
    efficiency: float = 1
    machine_options: list[MachineOption] | None = None

    def __hash__(self) -> int:
        return self.item.__hash__()

    def __str__(self):
        if all(v < 0 for v in self.voltage_tiers):
            repr_string = f'{self.name}'
        elif len(self.voltage_tiers) == 1:
            repr_string = f'{self.name} ({VoltageTier.voltage_tier_name(self.voltage_tiers[0])})'
        else:
            repr_string = f'{self.name}'
        return repr_string if not self.deprecated else repr_string + ' (DEPRECATED)'

    def minimal_voltage_tier(self) -> int:
        return min(self.voltage_tiers) if self.voltage_tiers else VoltageTier.NO_REQUIREMENT

    @property
    def voltage_tier(self) -> int:
        return self._voltage_tier

    def set_voltage_tier(self, voltage_tier: int) -> None:
        if voltage_tier in self.voltage_tiers:
            self._voltage_tier = voltage_tier
        else:
            _LOGGER.info(f'Cannot set voltage tier {voltage_tier} for machine {self}')

    def fit_recipe(self, raw_recipe: RawRecipe, log=False) -> RawRecipe:
        return self.machine_behaviour.fit_recipe(
            raw_recipe=raw_recipe,
            voltage_tier=self.voltage_tier,
            machine_options=self.machine_options,
            log=log
        )


@dataclass
class MachineType:
    name: str
    machines: list[Machine]

    def __hash__(self) -> int:
        return self.name.__hash__()

    def __repr__(self):
        return f'{self.name}'
