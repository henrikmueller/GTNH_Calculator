from .material import Material
from .voltage_tiers import VoltageTier


class Machine:
    name: str
    parallels: int
    voltage_tier: int
    requirements: list[Material]

    def __init__(
            self,
            name: str,
            parallels: int,
            voltage_tier: int
    ):
        self.name = name
        self.parallels = parallels
        self.voltage_tier = voltage_tier

    def __repr__(self) -> str:
        return self.name

    @property
    def voltage_tier_name(self) -> str:
        return VoltageTier.voltage_tier_name(self.voltage_tier)
