from __future__ import annotations
from dataclasses import dataclass
from typing import Dict
import logging
import yaml
from marshmallow import Schema, fields, post_load

from .machine_types import MachineType, MachineTypeSchema

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass
class MachineTypeBook:
    machine_types: Dict[str, list[MachineType]]

    def get_parallel_option(self, base_machine_type: MachineType) -> MachineType:
        machine_type_options = self.get_machine_type_options(base_machine_type)
        if len(machine_type_options) >= 2:
            return machine_type_options[1]
        return base_machine_type

    def get_machine_type_options(self, base_machine_type: MachineType) -> list[MachineType]:
        for machine_type_options in self.machine_types.values():
            if base_machine_type in machine_type_options:
                if base_machine_type.name == 'Large Chemical Reactor':
                    return [t for t in machine_type_options if t.name != 'Chemical Reactor']
                return machine_type_options
        return []

    def get_machine_type(self, machine_type_name: str) -> MachineType | None:
        for types in self.machine_types.values():
            for machine_type in types:
                if machine_type.name == machine_type_name:
                    return machine_type
        _LOGGER.warning(f'Machine type not found: {machine_type_name}')
        return None

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
