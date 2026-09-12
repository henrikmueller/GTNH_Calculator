from __future__ import annotations
import logging
import sys
from dataclasses import dataclass
from abc import ABC, abstractmethod

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


@dataclass(frozen=True)
class SheetEntry(ABC):
    @abstractmethod
    def is_duplicate_of(self, other: SheetEntry) -> bool:
        ...


@dataclass(frozen=True)
class MaterialEntry(SheetEntry):
    factory_id: str
    material_id: str
    material_name: str
    amount: float

    def is_duplicate_of(self, other: SheetEntry) -> bool:
        if not isinstance(other, MaterialEntry):
            return False
        return (
            self.material_id == other.material_id and
            self.factory_id == other.factory_id
        )


@dataclass(frozen=True)
class FactoryEntry(SheetEntry):
    factory_id: str
    factory_medium_id: str
    processing_time: float
    average_eu_per_tick: float
    conditions: str
    location: str
    comment: str

    def is_duplicate_of(self, other: SheetEntry) -> bool:
        if not isinstance(other, FactoryEntry):
            return False
        return self.factory_id == other.factory_id and self.factory_medium_id == other.factory_medium_id
