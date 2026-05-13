from dataclasses import dataclass
import logging
from enum import StrEnum
from typing import Dict
from math import nan

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


class MachineStatType(StrEnum):
    FUSION_TIER = 'fusion_tier'


@dataclass
class MachineStats:
    voltage_tiers: list[int]
    additional_stats: Dict[MachineStatType, float]
    efficiency: float = 1

    @property
    def fusion_tier(self) -> float:
        if MachineStatType.FUSION_TIER in self.additional_stats:
            return self.additional_stats[MachineStatType.FUSION_TIER]
        return nan
