from __future__ import annotations
from dataclasses import dataclass
from .material import Material
from .voltage_tiers import VoltageTier


@dataclass
class Machine:
    name: str
    multiblock: bool
    deprecated: bool
    disabled: bool
    voltage_tiers: list[int]
    item: Material
    machine_types: set[MachineType]

    def __hash__(self) -> int:
        return self.item.__hash__()

    def __repr__(self):
        if all(v < 0 for v in self.voltage_tiers):
            return f'{self.name}'
        if len(self.voltage_tiers) == 1:
            return f'{self.name} ({VoltageTier.voltage_tier_name(self.voltage_tiers[0])})'
        return f'{self.name}'

    def minimal_voltage_tier(self) -> int:
        return min(self.voltage_tiers) if self.voltage_tiers else VoltageTier.NO_REQUIREMENT


@dataclass
class MachineType:
    name: str
    machines: list[Machine]

    def __hash__(self) -> int:
        return self.name.__hash__()

    def __repr__(self):
        return f'{self.name}'
