from __future__ import annotations
from dataclasses import dataclass
import logging
import re
from typing import Any
from enum import Enum
from abc import abstractmethod

from ..utility.constants import STARTING_MATERIAL_NAMES

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


class MaterialType(str, Enum):
    ITEM = 'item'
    FLUID = 'fluid'


@dataclass
class Material:
    id: str
    image_file_path: str
    name: str
    mod: str
    nbt: str
    tooltip: str
    material_type: MaterialType

    def __init__(
        self,
        id: str,
        image_file_path: str,
        name: str,
        mod: str,
        nbt: str,
        tooltip: str = ''
    ):
        self.id = id
        self.image_file_path = image_file_path
        self.name = re.sub(r'§.', '', name)  # remove formatting symbols of the form "$*"
        self.mod = mod
        self.nbt = nbt
        self.tooltip = tooltip

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self):
        return self.name

    def __eq__(self, other: Any):
        return isinstance(other, Material) and self.id == other.id

    def is_ore(self) -> bool:
        return not self.is_fluid() and ' Ore ' in self.tooltip

    def is_starting(self) -> bool:
        return (
            self.is_ore() or self.name in STARTING_MATERIAL_NAMES or 
            (self.name == 'Crafting Table' and self.mod == 'minecraft')
            )

    @abstractmethod
    def is_fluid(self) -> bool:
        pass


class ExtractedItem(Material):
    fluid_amount: int
    empty_fluid_container: ExtractedItem | None
    fluid: ExtractedFluid | None
    material_type: MaterialType

    def __init__(
        self,
        id: str,
        image_file_path: str,
        name: str,
        mod: str,
        nbt: str,
        tooltip: str,
        fluid_amount: int,
        empty_fluid_container: ExtractedItem | None,
        fluid: ExtractedFluid | None
    ):
        super().__init__(id, image_file_path, name, mod, nbt)
        self.tooltip = tooltip
        self.fluid_amount = fluid_amount
        self.empty_fluid_container = empty_fluid_container
        self.fluid = fluid
        self.material_type = MaterialType.ITEM

    def __hash__(self) -> int:
        return super().__hash__()

    def __repr__(self):
        return self.name

    def is_fluid(self) -> bool:
        return False


class ExtractedFluid(Material):
    def __init__(
        self,
        id: str,
        image_file_path: str,
        name: str,
        mod: str,
        nbt: str,
        tooltip: str = ''
    ):
        super().__init__(id, image_file_path, name, mod, nbt, tooltip)
        self.material_type = MaterialType.FLUID

    def __hash__(self) -> int:
        return super().__hash__()

    def __repr__(self):
        return self.name

    def is_fluid(self) -> bool:
        return True


@dataclass
class MaterialGroup:
    materials: list[Material]

    def __len__(self):
        return len(self.materials)

    def __hash__(self) -> int:
        return self.materials[0].__hash__() if self.materials else 0

    def __repr__(self):
        return f'{[m for m in self.materials]}'

    def __eq__(self, other: Any):
        return isinstance(other, MaterialGroup) and set(self.materials) == set(other.materials)
