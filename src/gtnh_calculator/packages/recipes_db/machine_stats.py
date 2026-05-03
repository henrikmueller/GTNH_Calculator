from dataclasses import dataclass
import logging

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.WARNING)


@dataclass
class MachineStats:
    voltage_tiers: list[int]
    _voltage_tier: int
    speedup: float = 1
    efficiency: float = 1

    @property
    def voltage_tier(self) -> int:
        return self._voltage_tier

    def set_voltage_tier(self, voltage_tier: int) -> bool:
        if voltage_tier in self.voltage_tiers:
            self._voltage_tier = voltage_tier
            return True
        else:
            _LOGGER.warning(f'Cannot set voltage tier {voltage_tier} for machine {self}')
            return False
