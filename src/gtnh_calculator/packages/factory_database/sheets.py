from __future__ import annotations
import logging
import sys
from dataclasses import dataclass
from abc import ABC, abstractmethod
from frozendict import frozendict
from typing import Mapping, TypeVar, Generic
from enum import StrEnum

from .sheet_entries import SheetEntry, MaterialEntry, FactoryEntry
from .constants import MATERIALS_GID, FACTORIES_GID, GID

logging.basicConfig(stream=sys.stdout)
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)


T = TypeVar("T", bound=SheetEntry)


class SheetType(StrEnum):
    MATERIALS = "Materials"
    FACTORIES = "Factories"


@dataclass(frozen=True)
class SheetMetadata(Generic[T]):
    gid: GID
    title: str
    entry_type: type[T]


@dataclass(frozen=True)
class Sheet(Generic[T]):
    metadata: SheetMetadata[T]
    entries: tuple[T, ...]

    @property
    def gid(self) -> GID:
        return self.metadata.gid

    @property
    def entry_type(self) -> type[T]:
        return self.metadata.entry_type

    def __hash__(self) -> int:
        return hash(self.gid)

    def __str__(self) -> str:
        return self.metadata.title


SHEET_METADATA: Mapping[SheetType, SheetMetadata] = frozendict({
    SheetType.MATERIALS: SheetMetadata[MaterialEntry](MATERIALS_GID, "Materials", MaterialEntry),
    SheetType.FACTORIES: SheetMetadata[FactoryEntry](FACTORIES_GID, "Factories", FactoryEntry),
})
