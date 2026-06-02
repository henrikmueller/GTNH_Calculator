from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Any
import ast
import logging
from frozendict import frozendict

from ..machine_options.machine_options import MachineOptions
from ..machine_options.machine_option_types import MachineOptionType

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass(frozen=True)
class ParallelBehaviour:
    parallels_per_voltage_tier: int

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
            case 'by_machine_option':
                parallels_dict = frozendict(ast.literal_eval(str(specification['parallels_dict']).strip()))
                if not (isinstance(parallels_dict, frozendict) and all(isinstance(v, int) for v in parallels_dict.values())):
                    _LOGGER.warning(f'Invalid parallels dict: {parallels_dict} for specification: {specification}')
                return ParallelByMachineOptionBehaviour(
                    parallels_per_voltage_tier=0,
                    machine_option_type=MachineOptionType(specification['machine_option_type']),
                    parallels_dict=parallels_dict
                )
            case 'eic':
                return EICParallelBehaviour(
                    base_parallels=specification['base_parallels'] \
                        if 'base_parallels' in specification.keys() else 1,
                    parallels_per_voltage_tier=specification['parallels_per_voltage_tier'] \
                        if 'parallels_per_voltage_tier' in specification.keys() else 0,
                )
            case _:
                return NotImplementedParallelBehaviour()


@dataclass(frozen=True)
class DefaultParallelBehaviour(ParallelBehaviour):
    base_parallels: int = 1
    parallels_per_voltage_tier: int = 0

    def get_parallels(self, voltage_tier: int, machine_options: MachineOptions) -> int:
        return self.base_parallels + voltage_tier * self.parallels_per_voltage_tier


@dataclass(frozen=True)
class ParallelByMachineOptionBehaviour(ParallelBehaviour):
    machine_option_type: MachineOptionType
    parallels_dict: frozendict[int, int]

    def get_parallels(self, voltage_tier: int, machine_options: MachineOptions) -> int:
        machine_option = machine_options.get_option(self.machine_option_type)
        return self.parallels_dict[machine_option.tier] if machine_option.tier in self.parallels_dict.keys() else 1


@dataclass(frozen=True)
class EICParallelBehaviour(ParallelBehaviour):
    base_parallels: int = 1
    parallels_per_voltage_tier: int = 0

    def get_parallels(self, voltage_tier: int, machine_options: MachineOptions) -> int:
        containment_block_tier = machine_options.get_option(MachineOptionType.CONTAINMENT_BLOCK).tier
        return 4 ** (containment_block_tier - 1)


@dataclass(frozen=True)
class NotImplementedParallelBehaviour(ParallelBehaviour):
    parallels_per_voltage_tier: int = 0
    
    def get_parallels(self, voltage_tier: int, machine_options: MachineOptions) -> int:
        raise NotImplementedError('Parallel Behaviour not implemented')
