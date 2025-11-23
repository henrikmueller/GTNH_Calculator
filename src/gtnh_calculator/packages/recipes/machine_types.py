from __future__ import annotations
from dataclasses import dataclass
import logging
from marshmallow import Schema, fields, post_load, validates, ValidationError

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class MachineType:
    name: str
    speedup: float = 1
    energy_multiplier: float = 1
    base_parallels: int = 1
    parallels_per_voltage_tier: int = 0
    efficiency: float = 1
    multiblock: bool = False


class MachineTypeSchema(Schema):
    name = fields.String(required=True)
    speedup = fields.Float(required=False)
    energy_multiplier = fields.Float(required=False)
    base_parallels = fields.Integer(required=False)
    parallels_per_voltage_tier = fields.Integer(required=False)
    efficiency = fields.Float(required=False)
    multiblock = fields.Bool(required=False)

    @post_load
    def create(self, data, **kwargs) -> MachineType:
        return MachineType(**data)

    @validates('speedup')
    def validate_speedup(self, speedup: float, data_key: str) -> None:
        if speedup <= 0:
            raise ValidationError(f'Speedup must be positive: "{speedup}"')

    @validates('energy_multiplier')
    def validate_energy_multiplier(self, energy_multiplier: float, data_key: str) -> None:
        if energy_multiplier < 0:
            raise ValidationError(f'Speedup must be non-negative: "{energy_multiplier}"')

    @validates('base_parallels')
    def validate_base_parallels(self, base_parallels: int, data_key: str) -> None:
        if base_parallels < 0:
            raise ValidationError(f'Base parallels must be at least 0: "{base_parallels}"')

    @validates('parallels_per_voltage_tier')
    def validate_parallels_per_voltage_tier(self, parallels_per_voltage_tier: int, data_key: str) -> None:
        if parallels_per_voltage_tier <= 0:
            raise ValidationError(f'Parallels per Voltage Tier must be at least 0: "{parallels_per_voltage_tier}"')

    @validates('efficiency')
    def validate_efficiency(self, efficiency: float, data_key: str) -> None:
        if efficiency < 0:
            raise ValidationError(f'Efficiency must be non-negative: "{efficiency}"')
