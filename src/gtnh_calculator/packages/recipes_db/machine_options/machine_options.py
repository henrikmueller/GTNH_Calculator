from __future__ import annotations
from abc import abstractmethod
import logging
from typing import Dict, Any

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
        self.options = options

    def __str__(self) -> str:
        return f'{self.name} ({self.options})'

    @property
    def tier(self) -> int:
        return self.options['tier'] if 'tier' in self.options else 0

    def fits(self, raw_option: str) -> bool:
        return raw_option == self.name

    @abstractmethod
    def __lt__(self, other: MachineOption) -> bool:
        ...

    def __le__(self, other: MachineOption) -> bool:
        return self == other or self < other

    @classmethod
    def maximum(cls, option1: MachineOption | None, option2: MachineOption | None) -> MachineOption | None:
        if option2 is None:
            return option1
        if option1 is None or option2 > option1:
            return option2
        return option1


class MachineOptionSchema(Schema):
    def __init__(self, *args, extracted_materials=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.extracted_materials = extracted_materials

    name = fields.String(required=True)
    option_type = fields.Enum(MachineOptionType, by_value=True, required=True)
    options = fields.Dict(keys=fields.String(), values=fields.Float(), required=False)

    @post_load
    def create(self, data, **kwargs) -> MachineOption:
        return MachineOption(
            extracted_materials=self.extracted_materials,
            **data
        )
