from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Any

from packages.recipes_db.machine_options.machine_option_types import MachineOptionType

from ..machine_options.machine_options import MachineOptions


@dataclass
class SpeedupBehaviour:
    @abstractmethod
    def get_speedup_multiplier(self, machine_options: MachineOptions) -> float:
        ...

    @classmethod
    def create_speedup_behaviour(cls, specification: Dict[str, Any] | None = None) -> SpeedupBehaviour:
        if specification is None:
            return DefaultSpeedupBehaviour()
        match specification['type']:
            case 'default':
                return DefaultSpeedupBehaviour(
                    speedup_multiplier=specification['speedup_multiplier'],
                )
            case 'coil_temperature':
                return CoilTemperatureSpeedupBehaviour(
                    speedup_multiplier=specification['speedup_multiplier'] \
                         if 'speedup_multiplier' in specification.keys() else 1.0,
                    base_speed=specification['base_speed'],
                    speed_per_coil_tier=specification['speed_per_coil_tier'],
                )
            case _:
                return NotImplementedSpeedupBehaviour()


@dataclass
class DefaultSpeedupBehaviour(SpeedupBehaviour):
    speedup_multiplier: float = 1

    def get_speedup_multiplier(self, machine_options: MachineOptions) -> float:
        return self.speedup_multiplier

@dataclass
class CoilTemperatureSpeedupBehaviour(SpeedupBehaviour):
    speedup_multiplier: float = 1
    base_speed: float = 1
    speed_per_coil_tier: float = 0

    def get_speedup_multiplier(self, machine_options: MachineOptions) -> float:
        coil_tier = machine_options.get_option(MachineOptionType.COIL).tier
        return self.speedup_multiplier * (self.base_speed + self.speed_per_coil_tier * coil_tier)


class NotImplementedSpeedupBehaviour(SpeedupBehaviour):
    def get_speedup_multiplier(self, machine_options: MachineOptions) -> float:
        raise NotImplementedError('Speedup Behaviour not implemented')
