from __future__ import annotations
from dataclasses import dataclass
import logging
from marshmallow import Schema, fields, post_load, validates, ValidationError

from .voltage_tiers import VoltageTier
from .machine_options.machine_options import MachineOptions

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
    parallel: bool = False
    unlock_tier: int = -1
    avoid_to_use: bool = False
    valid_machine_options: tuple[str] = tuple()

    def unlock_tier_name(self) -> str:
        if self.unlock_tier < 0:
            return 'No unlock tier'
        return VoltageTier.voltage_tier_name(self.unlock_tier)

    @property
    def weight(self) -> float:
        return 10 if self.multiblock else 1


class MachineTypeSchema(Schema):
    name = fields.String(required=True)
    speedup = fields.Float(required=False)
    energy_multiplier = fields.Float(required=False)
    base_parallels = fields.Integer(required=False)
    parallels_per_voltage_tier = fields.Integer(required=False)
    efficiency = fields.Float(required=False)
    multiblock = fields.Bool(required=False)
    parallel = fields.Bool(required=False)
    unlock_tier = fields.String(required=False)
    avoid_to_use = fields.Bool(required=False)
    valid_machine_options = fields.List(fields.Str(), required=False)

    @post_load
    def create(self, data, **kwargs) -> MachineType:
        if 'unlock_tier' in data.keys():
            data['unlock_tier'] = VoltageTier.to_voltage_tier(data['unlock_tier'])
        if 'valid_machine_options' in data.keys():
            data['valid_machine_options'] = tuple(data['valid_machine_options'])
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

    @validates('unlock_tier')
    def validate_unlock_tier(self, unlock_tier: str, data_key: str) -> None:
        if unlock_tier not in VoltageTier.voltage_tiers(minimum=0):
            s = ", ".join(VoltageTier.voltage_tiers(minimum=0))
            raise ValidationError(f'Unlock tier must be one of the following: "{s}"')

    @validates('valid_machine_options')
    def validate_valid_machine_options(self, valid_machine_options: list[str], data_key: str) -> None:
        if not all(option in MachineOptions.all_option_types() for option in valid_machine_options):
            s = ", ".join(MachineOptions.all_option_types())
            raise ValidationError(f'Only the following valid machine options are allowed: "{s}"')
