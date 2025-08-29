from asyncio.windows_events import INFINITE
from dataclasses import dataclass
from typing import Callable
from math import log, floor
import logging

from .voltage_tiers import VoltageTier

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class ParallelData:
    name: str
    speedup: float
    energy_multiplier: float
    parallels: Callable[[int], int]
    perfect_overclocks: int

    def get_parallels(self, voltage_tier: int) -> int:
        if voltage_tier >= 1:
            return self.parallels(voltage_tier)
        return 1

    def effective_parallels_and_overclocks(self, eu_per_tick: float, voltage_tier: int) -> tuple[int, int]:
        max_eu_per_tick = VoltageTier.eu_per_tick(voltage_tier)
        reduced_eu_per_tick = self.energy_multiplier * eu_per_tick
        effective_parallels = min(floor(max_eu_per_tick // reduced_eu_per_tick), self.get_parallels(voltage_tier))
        overclocks = floor(log(max_eu_per_tick // (effective_parallels * reduced_eu_per_tick), 4))
        return effective_parallels, overclocks


INFINITE_PERFECT_OVERCLOCKS = 100
data = {
    'Sifter': ParallelData('Large Sifter Control Block', 5, 0.75, lambda v: 4 * v, 0),
    'Chemical Reactor': ParallelData('Large Chemical Reactor', 1, 1, lambda v: v, INFINITE_PERFECT_OVERCLOCKS),
    'Centrifuge': ParallelData('Industrial Centrifuge', 2.25, 0.9, lambda v: 6 * v, 0),
    'Electrolyzer': ParallelData('Industrial Electrolyzer', 2.8, 0.9, lambda v: 2 * v, 0),
    'Chemical Bath': ParallelData('Chemical Bath Multiblock', 5, 1, lambda v: 4 * v, 0),
    'Macerator': ParallelData('Industrial Maceration Stack (Upgraded)', 1.6, 1, lambda v: 8 * v, 0),
    'Distillation Tower': ParallelData('Dangote Distillus (Upgraded)', 3.5, 1, lambda v: 12, 0)
}


def parallel_machine_data(name: str) -> ParallelData:
    if name in data.keys():
        return data[name]
    _LOGGER.warning(f'No multiblock found for {name}.')
    return ParallelData(name, 1, 1, lambda v: 1, 0)
