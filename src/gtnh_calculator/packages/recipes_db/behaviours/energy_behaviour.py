from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Any

from ..machine_options.machine_options import MachineOption


@dataclass
class EnergyBehaviour:
    @abstractmethod
    def get_energy_multiplier(self, voltage_tier: int, machine_options: list[MachineOption] | None) -> float:
        ...

    @classmethod
    def create_energy_behaviour(cls, specification: Dict[str, Any] | None = None) -> EnergyBehaviour:
        if specification is None:
            return DefaultEnergyBehaviour()
        match specification['type']:
            case 'default':
                return DefaultEnergyBehaviour(
                    energy_multiplier=specification['energy_multiplier'],
                )
            case _:
                return NotImplementedEnergyBehaviour()


@dataclass
class DefaultEnergyBehaviour(EnergyBehaviour):
    energy_multiplier: float = 1

    def get_energy_multiplier(self, voltage_tier: int, machine_options: list[MachineOption] | None) -> float:
        return self.energy_multiplier


class NotImplementedEnergyBehaviour(EnergyBehaviour):
    def get_energy_multiplier(self, voltage_tier: int, machine_options: list[MachineOption] | None) -> float:
        raise NotImplementedError('Energy Behaviour not implemented')
