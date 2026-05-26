from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass
from typing import Dict, Any
from math import nan, isnan

from ..recipe_options import RecipeOptions
from ..machine_options.machine_options import MachineOptions
from ..machine_options.machine_option_types import MachineOptionType


@dataclass(frozen=True, slots=True)
class EnergyContext:
    machine_options: MachineOptions
    recipe_options: RecipeOptions
    machine_heat_capacity: float


@dataclass(frozen=True)
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
                    energy_multiplier=specification['energy_multiplier'] \
                        if 'energy_multiplier' in specification.keys() else 1,
                )
            case 'coil_tier':
                return CoilTierEnergyBehaviour(
                    energy_multiplier=specification['energy_multiplier'] \
                        if 'energy_multiplier' in specification.keys() else 1,
                    multiplier_per_coil_tier=specification['multiplier_per_coil_tier'],
                    minimal_multiplier=specification['minimal_multiplier'],
                )
            case 'coil_temperature':
                return CoilTemperatureEnergyBehaviour(
                    energy_multiplier=specification['energy_multiplier'] \
                        if 'energy_multiplier' in specification.keys() else 1,
                )
            case _:
                return NotImplementedEnergyBehaviour()


@dataclass(frozen=True)
class DefaultEnergyBehaviour(EnergyBehaviour):
    energy_multiplier: float = 1

    def get_energy_multiplier(self, context: EnergyContext) -> float:
        return self.energy_multiplier

@dataclass(frozen=True)
class CoilTierEnergyBehaviour(EnergyBehaviour):
    energy_multiplier: float = 1
    multiplier_per_coil_tier: float = 0
    minimal_multiplier: float = nan

    def get_energy_multiplier(self, context: EnergyContext) -> float:
        coil = context.machine_options.get_option(MachineOptionType.COIL)
        if isnan(self.minimal_multiplier):
            return self.energy_multiplier * (1 - self.multiplier_per_coil_tier * coil.tier)
        return self.energy_multiplier * max(1 - self.multiplier_per_coil_tier * coil.tier, self.minimal_multiplier)

@dataclass(frozen=True)
class CoilTemperatureEnergyBehaviour(EnergyBehaviour):
    energy_multiplier: float = 1

    def get_energy_multiplier(self, context: EnergyContext) -> float:
        return self.energy_multiplier * 0.95 ** max(
            (context.machine_heat_capacity - context.recipe_options.coil_heat) // 900, 0)


@dataclass(frozen=True)
class NotImplementedEnergyBehaviour(EnergyBehaviour):
    def get_energy_multiplier(self, context: EnergyContext) -> float:
        raise NotImplementedError('Energy Behaviour not implemented')
