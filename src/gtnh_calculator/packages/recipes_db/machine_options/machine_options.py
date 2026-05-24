from __future__ import annotations
from abc import abstractmethod
import logging
from typing import Dict, Any
from math import nan

from attr import dataclass
from marshmallow import Schema, fields, post_load, validates, ValidationError
from ...recipes_db.material import Material
from .machine_option_types import MachineOptionType

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


"""
------------------------------------------------------------------------------------------------------------------------
    Abstract Machine Options
------------------------------------------------------------------------------------------------------------------------
"""


@dataclass
class MachineOptions:
    valid_options: tuple[MachineOptionType, ...]
    _options: Dict[MachineOptionType, MachineOption]

    def has_option(self, type: MachineOptionType) -> bool:
        return type in self._options.keys()

    def get_option(self, type: MachineOptionType) -> MachineOption:
        return self._options[type]

    def set_option(self, type: MachineOptionType, option: MachineOption) -> None:
        if type not in self.valid_options:
            raise ValueError(f'MachineOptionType {type} not valid for {self}')
        self._options[type] = option

    def __repr__(self) -> str:
        return f'MachineOptions(valid={self.valid_options}, options={[o.__repr__() for o in self._options.values()]})'


class MachineOption:
    name: str
    option_type: MachineOptionType
    options: Dict[str, float]
    material: Material | None

    def __init__(
        self, extracted_materials: Dict[str, Material], name: str, option_type: MachineOptionType,
            options: Dict[str, float] | None = None
    ):
        self.material = extracted_materials[name]
        self.name = self.material.name
        self.option_type = option_type
        self.options = {} if options is None else options

    def __repr__(self) -> str:
        return f'{self.name} ({self.options})' if self.options else self.name

    def __str__(self) -> str:
        return f'{self.name} ({self.options})' if self.options else self.name

    @property
    def tier(self) -> int:
        return int(self.options['tier']) if 'tier' in self.options else 0

    @property
    def temperature(self) -> float:
        if 'temperature' in self.options:
            return self.options['temperature']
        return nan


class MachineOptionSchema(Schema):
    def __init__(self, *args, extracted_materials=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.extracted_materials: Dict[str, Material] = extracted_materials

    name = fields.String(required=True)
    option_type = fields.Enum(MachineOptionType, by_value=True, required=True)
    options = fields.Dict(keys=fields.String(), values=fields.Float(), required=False)

    @post_load
    def create(self, data, **kwargs) -> MachineOption:
        return MachineOption(
            extracted_materials=self.extracted_materials,
            **data
        )
