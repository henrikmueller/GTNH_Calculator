from __future__ import annotations
from abc import abstractmethod
from typing import Dict
from math import floor, log


class OverclockBehaviour:
    @abstractmethod
    def get_overclocks(self, current_eu_per_tick: float, max_eu_per_tick: float) -> tuple[int, int]:
        """
        :param current_eu_per_tick: EU/t of the recipe multiplied with parallels
        :param max_eu_per_tick: Max EU/t of the machine
        :return: Tuple of non-perfect and perfect overclocks
        """
        ...

    @classmethod
    def create_overclock_behaviour(cls, specification: Dict[str, str] | None = None) -> OverclockBehaviour:
        if specification is None:
            return DefaultOverclockBehaviour()
        match specification['type']:
            case 'infinite':
                return InfiniteOverclockBehaviour()
            case 'coil_temperature':
                return CoilTemperatureOverclockBehaviour()
        return NotImplementedOverclockBehaviour()


class DefaultOverclockBehaviour(OverclockBehaviour):
    def get_overclocks(self, current_eu_per_tick: float, max_eu_per_tick: float) -> tuple[int, int]:
        overclocks = floor(log(max_eu_per_tick // current_eu_per_tick, 4)) if current_eu_per_tick > 0 else 0
        return overclocks, 0


class InfiniteOverclockBehaviour(OverclockBehaviour):
    def get_overclocks(self, current_eu_per_tick: float, max_eu_per_tick: float) -> tuple[int, int]:
        overclocks = floor(log(max_eu_per_tick // current_eu_per_tick, 4)) if current_eu_per_tick > 0 else 0
        return 0, overclocks


class CoilTemperatureOverclockBehaviour(OverclockBehaviour):
    def get_overclocks(self, current_eu_per_tick: float, max_eu_per_tick: float) -> tuple[int, int]:
        overclocks = floor(log(max_eu_per_tick // current_eu_per_tick, 4)) if current_eu_per_tick > 0 else 0
        return overclocks, 0
        # TODO: raise NotImplementedError('Overclock Behaviour not implemented')


class NotImplementedOverclockBehaviour(OverclockBehaviour):
    def get_overclocks(self, current_eu_per_tick: float, max_eu_per_tick: float) -> tuple[int, int]:
        raise NotImplementedError('Overclock Behaviour not implemented')
