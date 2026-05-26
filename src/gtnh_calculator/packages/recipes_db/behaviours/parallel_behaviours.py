from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Any

from ..machine_options.machine_options import MachineOptions
from ..machine_options.machine_option_types import MachineOptionType


@dataclass
class ParallelBehaviour:
    base_parallels: int = 1
    parallels_per_voltage_tier: int = 0

    @abstractmethod
    def get_parallels(self, voltage_tier: int, machine_options: MachineOptions) -> int:
        ...

    @classmethod
    def create_parallel_behaviour(cls, specification: Dict[str, Any] | None = None) -> ParallelBehaviour:
        if specification is None:
            return DefaultParallelBehaviour()
        match specification['type']:
            case 'default':
                return DefaultParallelBehaviour(
                    base_parallels=specification['base_parallels'] \
                        if 'base_parallels' in specification.keys() else 1,
                    parallels_per_voltage_tier=specification['parallels_per_voltage_tier'] \
                        if 'parallels_per_voltage_tier' in specification.keys() else 0,
                )
            case 'default':
                return EICParallelBehaviour()
            case _:
                return NotImplementedParallelBehaviour()


@dataclass
class DefaultParallelBehaviour(ParallelBehaviour):
    base_parallels: int = 1
    parallels_per_voltage_tier: int = 0

    def get_parallels(self, voltage_tier: int, machine_options: MachineOptions) -> int:
        return self.base_parallels + voltage_tier * self.parallels_per_voltage_tier


@dataclass
class EICParallelBehaviour(ParallelBehaviour):
    base_parallels: int = 1
    parallels_per_voltage_tier: int = 0

    def get_parallels(self, voltage_tier: int, machine_options: MachineOptions) -> int:
        containment_block_tier = machine_options.get_option(MachineOptionType.CONTAINMENT_BLOCK).tier
        return 4 ** (containment_block_tier - 1)


class NotImplementedParallelBehaviour(ParallelBehaviour):
    base_parallels: int = 1
    parallels_per_voltage_tier: int = 0
    
    def get_parallels(self, voltage_tier: int, machine_options: MachineOptions) -> int:
        raise NotImplementedError('Parallel Behaviour not implemented')
