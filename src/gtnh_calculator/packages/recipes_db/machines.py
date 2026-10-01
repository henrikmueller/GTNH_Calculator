from __future__ import annotations
import logging
from dataclasses import dataclass, field
from math import nan
from typing import Dict, Iterable
from collections import defaultdict

from .material import Material
from .voltage_tiers import VoltageTier
from .machine_options.machine_option_types import MachineOptionType
from .behaviours.machine_behaviours import MachineBehaviour
from .behaviours.capacity_utilization_behaviour import CapacityUtilizationBehaviour
from .machine_stats import MachineStats

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


def get_machine_type_counts(machines: Iterable[Machine]) -> Dict[MachineType, int]:
    counts: Dict[MachineType, int] = defaultdict(int)
    for machine in machines:
        for machine_type in machine.machine_types:
            counts[machine_type] += 1
    return counts


def get_prominent_machine_type(machines: Iterable[Machine], ratio_threshold: float = 2.0) -> MachineType | None:
    counts = get_machine_type_counts(machines)
    if not counts:
        return None
    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_counts) == 1:
        return sorted_counts[0][0]
    if sorted_counts[0][1] > sorted_counts[1][1] and sorted_counts[0][1] / sorted_counts[1][1] >= ratio_threshold:
        return sorted_counts[0][0]
    return None


@dataclass(frozen=True)
class MachineMode:
    name: str
    id_suffix: str
    machine_types: tuple[MachineType, ...]
    default: bool = True


@dataclass(frozen=True)
class Machine:
    name: str
    mode: MachineMode
    multiblock: bool
    deprecated: bool
    disabled: bool
    unspecified: bool
    item: Material
    weight: int
    machine_behaviour: MachineBehaviour
    capacity_utilization_behaviour: CapacityUtilizationBehaviour
    valid_options: tuple[MachineOptionType, ...]
    machine_stats: MachineStats
    specified_unlock_tier: int

    @property
    def database_id(self) -> str:
        return self.item.id

    @property
    def id(self) -> str:
        return self.item.id + self.mode.id_suffix

    @property
    def voltage_tiers(self) -> tuple[int, ...]:
        return self.machine_stats.voltage_tiers

    @property
    def machine_types(self) -> tuple[MachineType, ...]:
        return self.mode.machine_types

    @property
    def in_default_mode(self) -> bool:
        return self.mode.default

    def __repr__(self):
        name = f'{self.name} ({self.mode.name})' if not self.mode.default else f'{self.name}'
        if all(v < 0 for v in self.voltage_tiers):
            repr_string = name
        elif len(self.voltage_tiers) == 1:
            repr_string = f'{name} ({VoltageTier.voltage_tier_name(self.voltage_tiers[0])})'
        else:
            repr_string = name
        return repr_string if not self.deprecated else repr_string + ' (DEPRECATED)'

    def __str__(self):
        name = f'{self.name} ({self.mode.name})' if not self.mode.default else f'{self.name}'
        if all(v < 0 for v in self.voltage_tiers):
            repr_string = name
        elif len(self.voltage_tiers) == 1:
            repr_string = f'{name} ({VoltageTier.voltage_tier_name(self.voltage_tiers[0])})'
        else:
            repr_string = name
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
