from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Any

from ..recipe_options import RecipeOptions


@dataclass(frozen=True, slots=True)
class EnergyContext:
    recipe_options: RecipeOptions
    machine_heat_capacity: float


@dataclass
class EnergyBehaviour:
    @abstractmethod
    def get_energy_multiplier(self, context: EnergyContext) -> float:
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
            case 'coil_temperature':
                return CoilTemperatureEnergyBehaviour(
                    energy_multiplier=specification['energy_multiplier'],
                )
            case _:
                return NotImplementedEnergyBehaviour()


@dataclass
class DefaultEnergyBehaviour(EnergyBehaviour):
    energy_multiplier: float = 1

    def get_energy_multiplier(self, context: EnergyContext) -> float:
        return self.energy_multiplier

@dataclass
class CoilTemperatureEnergyBehaviour(EnergyBehaviour):
    energy_multiplier: float = 1

    def get_energy_multiplier(self, context: EnergyContext) -> float:
        return self.energy_multiplier * 0.95 ** max(
            (context.machine_heat_capacity - context.recipe_options.temperature) // 900, 0)


class NotImplementedEnergyBehaviour(EnergyBehaviour):
    def get_energy_multiplier(self, context: EnergyContext) -> float:
        raise NotImplementedError('Energy Behaviour not implemented')
