from __future__ import annotations
from abc import abstractmethod
from typing import Dict, Any
from math import floor, log, isnan
from dataclasses import dataclass

from ..recipe_options import RecipeOptions
from ..machine_stats import MachineStats, MachineStatType
from packages.recipes_db import recipe_options


@dataclass(frozen=True, slots=True)
class OverclockContext:
    current_eu_per_tick: float
    max_eu_per_tick: float
    max_overclocks: int
    machine_stats: MachineStats
    recipe_options: RecipeOptions
    machine_heat_capacity: float


class OverclockBehaviour:
    @abstractmethod
    def get_overclocks(self, context: OverclockContext) -> tuple[int, int]:
        """
        :param current_eu_per_tick: EU/t of the recipe multiplied with parallels
        :param max_eu_per_tick: Max EU/t of the machine
        :param max_overclocks: Maximal amount of overclocks of the machine
        :return: Tuple of non-perfect and perfect overclocks
        """
        ...

    @abstractmethod
    def get_max_overclocks(
        self, voltage_tier: int
    ) -> int:
        """
        :param voltage_tier: Voltage tier of the machine
        :return: Tuple of non-perfect and perfect overclocks
        """
        ...

    @classmethod
    def create_overclock_behaviour(cls, specification: Dict[str, Any] | None = None) -> OverclockBehaviour:
        if specification is None:
            return DefaultOverclockBehaviour()
        match specification['type']:
            case 'default':
                return DefaultOverclockBehaviour(
                    maximal_overclocks=int(specification['maximal_overclocks']),
                )
            case 'infinite':
                return InfiniteOverclockBehaviour()
            case 'fusion':
                return FusionOverclockBehaviour(
                    perfect_overclocks=specification['perfect_overclocks'] \
                        if 'perfect_overclocks' in specification.keys() else False
                )
            case 'coil_temperature':
                return CoilTemperatureOverclockBehaviour()
        return NotImplementedOverclockBehaviour()


@dataclass
class DefaultOverclockBehaviour(OverclockBehaviour):
    maximal_overclocks: int | None = None

    def get_overclocks(self, context: OverclockContext) -> tuple[int, int]:
        overclocks = min(
            floor(log(context.max_eu_per_tick // context.current_eu_per_tick, 4)) 
            if context.current_eu_per_tick > 0 else 0, context.max_overclocks
        )
        return overclocks, 0

    def get_max_overclocks(
        self, voltage_tier: int
    ) -> int:
        return voltage_tier - 1 if self.maximal_overclocks is None else min(voltage_tier - 1, self.maximal_overclocks)


@dataclass
class InfiniteOverclockBehaviour(OverclockBehaviour):
    def get_overclocks(self, context: OverclockContext) -> tuple[int, int]:
        overclocks = min(
            floor(log(context.max_eu_per_tick // context.current_eu_per_tick, 4)) 
            if context.current_eu_per_tick > 0 else 0, context.max_overclocks
        )
        return 0, overclocks

    def get_max_overclocks(
        self, voltage_tier: int
    ) -> int:
        return voltage_tier - 1


@dataclass
class FusionOverclockBehaviour(OverclockBehaviour):
    perfect_overclocks: bool = False

    def get_overclocks(self, context: OverclockContext) -> tuple[int, int]:
        overclocks = min(
            floor(log(context.max_eu_per_tick // context.current_eu_per_tick, 4)) 
            if context.current_eu_per_tick > 0 else 0, context.max_overclocks
        )
        fusion_tier_difference = max(int(context.machine_stats.fusion_tier - context.recipe_options.fusion_tier), 0)
        overclocks = min(overclocks, fusion_tier_difference)
        return (0, overclocks) if self.perfect_overclocks else (overclocks, 0)

    def get_max_overclocks(
        self, voltage_tier: int
    ) -> int:
        return voltage_tier - 1


@dataclass
class CoilTemperatureOverclockBehaviour(OverclockBehaviour):
    def get_overclocks(self, context: OverclockContext) -> tuple[int, int]:
        recipe_temperature = context.recipe_options.coil_heat
        if recipe_temperature is None:
            raise ValueError(f'Invalid recipe temperature {recipe_temperature} for CoilTemperatureOverclockBehaviour')
        
        overclocks = min(
            floor(log(context.max_eu_per_tick // context.current_eu_per_tick, 4)) 
            if context.current_eu_per_tick > 0 else 0, context.max_overclocks
        )
        max_perfect_overclocks = max((context.machine_heat_capacity - context.recipe_options.coil_heat) // 1800, 0)
        perfect_overclocks = overclocks if isnan(max_perfect_overclocks) \
            else int(min(overclocks, max_perfect_overclocks))
        return overclocks - perfect_overclocks, perfect_overclocks

    def get_max_overclocks(
        self, voltage_tier: int
    ) -> int:
        return voltage_tier - 1


@dataclass
class NotImplementedOverclockBehaviour(OverclockBehaviour):
    def get_overclocks(self, context: OverclockContext) -> tuple[int, int]:
        raise NotImplementedError('Overclock Behaviour not implemented')

    def get_max_overclocks(
        self, voltage_tier: int
    ) -> int:
        raise NotImplementedError('Overclock Behaviour not implemented')
