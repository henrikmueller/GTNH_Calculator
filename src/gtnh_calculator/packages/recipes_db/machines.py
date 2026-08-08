from __future__ import annotations
import logging
from dataclasses import dataclass, field
from math import nan
from typing import Dict

from .material import Material
from .voltage_tiers import VoltageTier
from .machine_options.machine_option_types import MachineOptionType
from .behaviours.machine_behaviours import MachineBehaviour
from .behaviours.capacity_utilization_behaviour import CapacityUtilizationBehaviour
from .machine_stats import MachineStats

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


@dataclass(frozen=True)
class Machine:
    name: str
    multiblock: bool
    deprecated: bool
    disabled: bool
    unspecified: bool
    item: Material
    weight: int
    machine_behaviour: MachineBehaviour
    capacity_utilization_behaviour: CapacityUtilizationBehaviour
    machine_types: tuple[MachineType, ...]
    valid_options: tuple[MachineOptionType, ...]
    machine_stats: MachineStats
    specified_unlock_tier: int

    @property
    def id(self) -> str:
        return self.item.id

    @property
    def voltage_tiers(self) -> tuple[int, ...]:
        return self.machine_stats.voltage_tiers

    def __repr__(self):
        if all(v < 0 for v in self.voltage_tiers):
            repr_string = f'{self.name}'
        elif len(self.voltage_tiers) == 1:
            repr_string = f'{self.name} ({VoltageTier.voltage_tier_name(self.voltage_tiers[0])})'
        else:
            repr_string = f'{self.name}'
        return repr_string if not self.deprecated else repr_string + ' (DEPRECATED)'

    def __str__(self):
        if all(v < 0 for v in self.voltage_tiers):
            repr_string = f'{self.name}'
        elif len(self.voltage_tiers) == 1:
            repr_string = f'{self.name} ({VoltageTier.voltage_tier_name(self.voltage_tiers[0])})'
        else:
            repr_string = f'{self.name}'
        return repr_string if not self.deprecated else repr_string + ' (DEPRECATED)'

    @property
    def machine_name_specified(self) -> str:
        if self.unspecified:
            return f'{self.__str__()} (Unspecified)'
        return self.__str__()

    def minimal_voltage_tier(self) -> int:
        return min(self.voltage_tiers) if self.voltage_tiers else VoltageTier.NO_REQUIREMENT

    @property
    def unlock_tier(self) -> int:
        return self.specified_unlock_tier


@dataclass(eq=True, frozen=True)
class MachineType:
    name: str
