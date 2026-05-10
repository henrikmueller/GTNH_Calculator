from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Any
from math import nan

from ..machine_options.machine_options import MachineOptions
from ..machine_options.machine_option_types import MachineOptionType


@dataclass
class HeatCapacityBehaviour:
    @abstractmethod
    def get_heat_capacity(
        self, machine_voltage_tier: int, machine_options: MachineOptions
    ) -> float:
        ...

    @classmethod
    def create_heat_capacity_behaviour(cls, specification: Dict[str, Any] | None = None) -> HeatCapacityBehaviour:
        if specification is None:
            return DefaultHeatCapacityBehaviour()
        match specification['type']:
            case 'default':
                return DefaultHeatCapacityBehaviour()
            case 'ebf':
                return EBFHeatCapacityBehaviour()
            case _:
                return NotImplementedHeatCapacityBehaviour()


@dataclass
class DefaultHeatCapacityBehaviour(HeatCapacityBehaviour):
    def get_heat_capacity(
        self, machine_voltage_tier: int, machine_options: MachineOptions
    ) -> float:
        if not machine_options.has_option(MachineOptionType.COIL):
            return nan
        return machine_options.get_option(MachineOptionType.COIL).temperature


@dataclass
class EBFHeatCapacityBehaviour(HeatCapacityBehaviour):
    def get_heat_capacity(
        self, machine_voltage_tier: int, machine_options: MachineOptions
    ) -> float:
        if not machine_options.has_option(MachineOptionType.COIL):
            return nan
        heat_capacity = machine_options.get_option(MachineOptionType.COIL).temperature
        return heat_capacity + 100 * max(machine_voltage_tier - 2, 0)


class NotImplementedHeatCapacityBehaviour(HeatCapacityBehaviour):
    def get_heat_capacity(
        self, machine_voltage_tier: int, machine_options: MachineOptions
    ) -> float:
        raise NotImplementedError('Energy Behaviour not implemented')
