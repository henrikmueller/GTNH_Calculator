from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
import yaml
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


class MachineTypeSchema(Schema):
    name = fields.String(required=True)
    speedup = fields.Float(required=False)
    energy_multiplier = fields.Float(required=False)
    base_parallels = fields.Integer(required=False)
    parallels_per_voltage_tier = fields.Integer(required=False)
    efficiency = fields.Float(required=False)

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
        if base_parallels <= 1:
            raise ValidationError(f'Base parallels must be at least 1: "{base_parallels}"')

    @validates('parallels_per_voltage_tier')
    def validate_parallels_per_voltage_tier(self, parallels_per_voltage_tier: int, data_key: str) -> None:
        if parallels_per_voltage_tier <= 0:
            raise ValidationError(f'Parallels per Voltage Tier must be at least 0: "{parallels_per_voltage_tier}"')

    @validates('efficiency')
    def validate_efficiency(self, efficiency: float, data_key: str) -> None:
        if efficiency < 0:
            raise ValidationError(f'Efficiency must be non-negative: "{efficiency}"')


@dataclass
class MachineTypeBook:
    machine_types: Dict[str, list[MachineType]]

    def get_default(self, machine_type: MachineType) -> MachineType:
        pass

    def get_machine_type(self, machine_type_name: str) -> MachineType:
        for types in self.machine_types.values():
            for machine_type in types:
                if machine_type.name == machine_type_name:
                    return machine_type
        _LOGGER.warning(f'Machine type not found: {machine_type_name}')

    @classmethod
    def load_machine_type_book(cls, path: str) -> MachineTypeBook:
        with open(path, 'r') as f:
            yaml_data = yaml.load(f, Loader=yaml.SafeLoader)
            schema = MachineTypeBookSchema()
            return schema.load(yaml_data)


class MachineTypeBookSchema(Schema):
    machine_types = fields.Dict(
        keys=fields.String(required=True),
        values=fields.List(fields.Nested(MachineTypeSchema, required=False), required=True)
    )

    @post_load
    def create(self, data, **kwargs) -> MachineTypeBook:
        return MachineTypeBook(**data)

