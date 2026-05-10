from dataclasses import dataclass
import logging

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


@dataclass
class MachineStats:
    voltage_tiers: list[int]
    efficiency: float = 1
